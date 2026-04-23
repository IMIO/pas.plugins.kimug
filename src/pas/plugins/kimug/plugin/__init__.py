from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from jwt import InvalidTokenError
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from pas.plugins.kimug.interfaces import IKimugPlugin
from pas.plugins.oidc.plugins import OIDCPlugin
from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from Products.PluggableAuthService.interfaces import plugins as pas_interfaces
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
        payload = self._decode_token(token)
        if payload is None:
            return None
        sub = payload.get("sub")
        if not sub:
            return None
        return sub, payload.get("email") or sub

    def _get_jwks_client(self):
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
            keycloak_url = os.environ["keycloak_url"].rstrip("/")
            realm = os.environ["keycloak_realm"]
            jwks_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/certs"
            cls._jwks_client = PyJWKClient(
                jwks_url,
                cache_keys=True,
                lifespan=cls._JWKS_CLIENT_TTL,
                timeout=5,
            )
            cls._jwks_client_created_at = now
        return cls._jwks_client

    def _decode_token(self, token):
        """Decode and fully verify a Keycloak-issued RS256 JWT.

        Verifies signature, ``alg``, ``iss``, ``aud``, ``exp``, ``iat``, and
        the presence of ``sub``. Returns the payload on success or ``None``
        on any failure. Never re-raises: returning None lets the PAS
        authentication chain fall through to other plugins instead of
        propagating to HTTP 500.
        """
        try:
            signing_key = self._get_jwks_client().get_signing_key_from_jwt(token)
        except PyJWKClientError as exc:
            logger.info("JWKS lookup failed: %s", exc)
            return None
        except Exception as exc:
            # Network, DNS, or misconfiguration. Degrade gracefully.
            logger.warning("JWKS unreachable: %s", exc)
            return None

        try:
            return jwt.decode(
                token,
                key=signing_key.key,
                algorithms=["RS256"],
                audience=os.environ.get("keycloak_audience", "account"),
                issuer=os.environ.get("keycloak_issuer"),
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


InitializeClass(KimugPlugin)
