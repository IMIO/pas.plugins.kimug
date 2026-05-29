from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from jwt import InvalidTokenError
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from pas.plugins.kimug.interfaces import IKimugPlugin
from pas.plugins.oidc.plugins import OIDCPlugin
from plone import api
from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from Products.PluggableAuthService.interfaces import plugins as pas_interfaces
from urllib.parse import urlparse
from zope.interface import implementer

import jwt
import logging
import os
import time


logger = logging.getLogger("pas.plugins.kimug")


def manage_addKimugPlugin(context, id="oidc", title="", RESPONSE=None, **kw):
    """Create an instance of a Kimug Plugin."""
    plugin = KimugPlugin(id, title, **kw)
    context._setObject(plugin.getId(), plugin)
    if RESPONSE is not None:
        RESPONSE.redirect("manage_workspace")


manage_addKimugPluginForm = PageTemplateFile(
    "www/KimugPluginForm", globals(), __name__="manage_addKimugluginForm"
)


@implementer(
    IKimugPlugin,
    pas_interfaces.IChallengePlugin,
    pas_interfaces.IRolesPlugin,
    pas_interfaces.IAuthenticationPlugin,
    pas_interfaces.IExtractionPlugin,
)
class KimugPlugin(OIDCPlugin):
    security = ClassSecurityInfo()
    meta_type = "Kimug Plugin"
    _dont_swallow_my_exceptions = True

    # JWKS client cache. Refreshed after ``_JWKS_CLIENT_TTL`` seconds so key
    # rotations on the Keycloak side are picked up without a restart.
    _jwks_client = None
    _jwks_client_created_at = 0.0
    _JWKS_CLIENT_TTL = 3600

    add_user_url: str = ""
    personal_information_url: str = ""
    change_password_url: str = ""
    _properties = list(OIDCPlugin._properties)
    _properties.append(
        {
            "id": "add_user_url",
            "type": "string",
            "mode": "w",
            "label": "Add User URL",
        }
    )
    _properties.append(
        {
            "id": "personal_information_url",
            "type": "string",
            "mode": "w",
            "label": "Personal Information URL",
        }
    )
    _properties.append(
        {
            "id": "change_password_url",
            "type": "string",
            "mode": "w",
            "label": "Change Password URL",
        }
    )
    _properties = tuple(_properties)

    @security.private
    def getRolesForPrincipal(self, user, request=None):
        """Fulfill RolesPlugin requirements"""
        app_id = os.environ.get("application_id", "iA.Smartweb")
        admin_group = f"{app_id}-admin"
        roles = ["Member"]
        if (
            app_id
            and admin_group in user.getGroups()
            and user.getProperty("email").endswith("@imio.be")
        ):
            roles.append("Manager")
            return tuple(roles)
        return tuple(roles)

    @security.private
    def extractCredentials(self, request):
        """Extract an OAuth2 bearer access token from the request.
        Implementation of IExtractionPlugin that extracts any 'Bearer' token
        from the HTTP 'Authorization' header.
        """
        # See RFC 6750 (2.1. Authorization Request Header Field) for details
        # on bearer token usage in OAuth2
        # https://tools.ietf.org/html/rfc6750#section-2.1

        creds = {}
        auth = request._auth
        if auth is None:
            return None
        if auth[:7].lower() == "bearer ":
            creds["token"] = auth.split()[-1]
        else:
            return None
        return creds

    @security.public
    def authenticateCredentials(self, credentials):
        """credentials -> (userid, login) | None

        - 'credentials' will be a mapping, as returned by IExtractionPlugin.
        - Return a tuple (user_id, login) if the bearer JWT verifies against
          Keycloak's JWKS, else None.
        """
        token = credentials.get("token")
        if not token:
            return None
        try:
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            issuer = unverified_payload.get("iss", "")
        except InvalidTokenError:
            return None
        if issuer.endswith("/realms/sso-apps"):
            # TODO (?): maybe we should get the access group name from the username
            access_group = os.environ.get(
                "SSO_APPS_ACCESS_GROUP", "access_imio-apps-kimug"
            )
            if access_group in unverified_payload.get("groups", []):
                plugin = "oidc_sso_apps"
            else:
                return None
        else:
            plugin = "oidc"
        payload = self._decode_token(token, plugin=plugin)
        if payload is None:
            return None
        sub = payload.get("sub")
        if not sub:
            return None
        self._ensure_user_exists(sub, payload)
        return sub, payload.get("email") or sub

    def _get_jwks_client(self, plugin="oidc"):
        """Return a cached PyJWKClient for the configured Keycloak realm.

        Client is rebuilt after ``_JWKS_CLIENT_TTL`` seconds. PyJWKClient
        itself caches signing keys keyed by ``kid`` and handles rotation.
        """
        # ``type(self)`` is the Acquisition wrapper, not KimugPlugin, so
        # writing to it silently fails to reach the class-level cache.
        # Reference the real class explicitly.
        cls = KimugPlugin
        now = time.time()
        if (
            cls._jwks_client is None
            or now - cls._jwks_client_created_at > cls._JWKS_CLIENT_TTL
        ):
            if plugin == "oidc":
                keycloak_url = os.environ.get(
                    "keycloak_url", "https://keycloak.127.0.0.1.nip.io/"
                ).rstrip("/")
                realm = os.environ.get("keycloak_realm", "plone")
            elif plugin == "oidc_sso_apps":
                sso_apps_url = os.environ.get(
                    "SSO_APPS_URL", "https://keycloak.127.0.0.1.nip.io/"
                ).rstrip("/")
                sso_apps_url_parsed = urlparse(sso_apps_url)
                keycloak_url = (
                    f"{sso_apps_url_parsed.scheme}://{sso_apps_url_parsed.netloc}"
                )
                realm = os.environ.get("SSO_APPS_REALM", "sso-apps")
            jwks_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/certs"
            cls._jwks_client = PyJWKClient(
                jwks_url,
                cache_keys=True,
                lifespan=cls._JWKS_CLIENT_TTL,
                timeout=5,
            )
            cls._jwks_client_created_at = now
        return cls._jwks_client

    def _decode_token(self, token, plugin="oidc"):
        """Decode and fully verify a Keycloak-issued RS256 JWT.

        Verifies signature, ``alg``, ``iss``, ``aud``, ``exp``, ``iat``, and
        the presence of ``sub``. Returns the payload on success or ``None``
        on any failure. Never re-raises: returning None lets the PAS
        authentication chain fall through to other plugins instead of
        propagating to HTTP 500.
        """
        try:
            # __import__("ipdb").set_trace()
            signing_key = self._get_jwks_client(plugin=plugin).get_signing_key_from_jwt(
                token
            )
        except PyJWKClientError as exc:
            logger.info("JWKS lookup failed: %s", exc)
            return None
        except Exception as exc:
            # Network, DNS, or misconfiguration. Degrade gracefully.
            logger.warning("JWKS unreachable: %s", exc)
            return None

        if plugin == "oidc":
            issuer = os.environ.get("keycloak_issuer")
            audience = os.environ.get("keycloak_audience", "account")
        elif plugin == "oidc_sso_apps":
            sso_apps_realm = os.environ.get("SSO_APPS_REALM", "sso-apps")
            sso_apps_url = os.environ.get(
                "SSO_APPS_URL", "https://keycloak.127.0.0.1.nip.io/"
            ).rstrip("/")
            sso_apps_url_parsed = urlparse(sso_apps_url)
            issuer = f"{sso_apps_url_parsed.scheme}://{sso_apps_url_parsed.netloc}/realms/{sso_apps_realm}"
            audience = os.environ.get("keycloak_audience", "account")
        try:
            return jwt.decode(
                token,
                key=signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
                options={
                    "require": ["exp", "iat", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except InvalidTokenError as exc:
            logger.info("JWT rejected: %s", exc)
            return None

    def _ensure_user_exists(self, userid, payload):
        if api.user.get(userid=userid) is not None:
            return
        try:
            new_user = self._create_user(userid)
        except Exception:
            logger.exception("Could not create local user for %s", userid)
            return
        userinfo = {
            "username": payload["email"],
            "email": payload["email"],
            "name": payload["preferred_username"],
        }
        try:
            self._update_user(new_user, userinfo, first_login=True)
        except Exception as e:
            logger.error(f"Not able to update user {payload['email']}, {e}")


InitializeClass(KimugPlugin)
