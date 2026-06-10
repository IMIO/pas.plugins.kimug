from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from jwt import InvalidTokenError
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from pas.plugins.kimug.interfaces import IKimugPlugin
from pas.plugins.kimug.utils import is_log_active
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
logger.setLevel(logging.INFO)


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

    # JWKS clients cached per realm (keyed by plugin id). Refreshed after
    # ``_JWKS_CLIENT_TTL`` seconds so key rotations on the Keycloak side are
    # picked up without a restart. A single shared client would be handed to
    # both the ``oidc`` and ``oidc_sso_apps`` realms, whose tokens then never
    # match the cached keyset and force a JWKS refetch on every request.
    _jwks_clients = {}  # plugin id -> PyJWKClient
    _jwks_clients_created_at = {}  # plugin id -> float (epoch)
    _JWKS_CLIENT_TTL = 3600

    # Per-realm JWKS failure backoff. After a failed fetch we skip further
    # fetches for ``_JWKS_FAILURE_COOLDOWN`` seconds, so a transient 403 from
    # the Keycloak proxy is not turned into a self-sustaining retry storm
    # (PyJWT clears its keyset cache on every failed fetch, which otherwise
    # makes the next request fetch again).
    _jwks_failed_at = {}  # plugin id -> epoch of last JWKS fetch failure
    _JWKS_FAILURE_COOLDOWN = 30  # seconds to skip JWKS fetches after a failure

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
        if is_log_active():
            logger.info(
                f"getRolesForPrincipal: user={user.getId()}, app_id={app_id}, "
                f"admin_group={admin_group}, groups={user.getGroups()}"
            )
        if (
            app_id
            and admin_group in user.getGroups()
            and user.getProperty("email").endswith("@imio.be")
        ):
            roles.append("Manager")
            if is_log_active():
                logger.info(f"getRolesForPrincipal: assigned roles={tuple(roles)}")
            return tuple(roles)
        if is_log_active():
            logger.info(f"getRolesForPrincipal: assigned roles={tuple(roles)}")
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
            if is_log_active():
                logger.info("Bearer token found in Authorization header")
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
        if is_log_active():
            logger.info(f"authenticateCredentials: token issuer={issuer}")
        if issuer.endswith("/realms/sso-apps"):
            # TODO (?): maybe we should get the access group name from the username
            access_group = os.environ.get(
                "SSO_APPS_ACCESS_GROUP", "access_imio-apps-kimug"
            )
            groups = unverified_payload.get("groups", [])
            if is_log_active():
                logger.info(
                    f"authenticateCredentials: sso-apps issuer detected, "
                    f"checking access_group='{access_group}', user groups={groups}"
                )
            if access_group in groups:
                plugin = "oidc_sso_apps"
            else:
                if is_log_active():
                    logger.info(
                        f"authenticateCredentials: access denied — "
                        f"'{access_group}' not in user groups"
                    )
                return None
        else:
            plugin = "oidc"
        if is_log_active():
            logger.info(f"authenticateCredentials: routing to plugin='{plugin}'")
        payload = self._decode_token(token, plugin=plugin)
        if payload is None:
            return None
        sub = payload.get("sub")
        if not sub:
            if is_log_active():
                logger.info("authenticateCredentials: token has no 'sub' claim")
            return None
        if is_log_active():
            logger.info(
                f"authenticateCredentials: token valid, "
                f"sub={sub}, email={payload.get('email')}"
            )
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
        created_at = cls._jwks_clients_created_at.get(plugin, 0.0)
        if plugin not in cls._jwks_clients or now - created_at > cls._JWKS_CLIENT_TTL:
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
            if is_log_active():
                logger.info(
                    f"_get_jwks_client: rebuilding JWKS client "
                    f"for plugin='{plugin}' ({jwks_url})"
                )
            cls._jwks_clients[plugin] = PyJWKClient(
                jwks_url,
                cache_keys=True,
                lifespan=cls._JWKS_CLIENT_TTL,
                timeout=5,
            )
            cls._jwks_clients_created_at[plugin] = now
        elif is_log_active():
            age = now - created_at
            logger.info(
                f"_get_jwks_client: reusing cached JWKS client "
                f"for plugin='{plugin}' (age={age:.0f}s)"
            )
        return cls._jwks_clients[plugin]

    def _decode_token(self, token, plugin="oidc"):
        """Decode and fully verify a Keycloak-issued RS256 JWT.

        Verifies signature, ``alg``, ``iss``, ``aud``, ``exp``, ``iat``, and
        the presence of ``sub``. Returns the payload on success or ``None``
        on any failure. Never re-raises: returning None lets the PAS
        authentication chain fall through to other plugins instead of
        propagating to HTTP 500.
        """
        cls = KimugPlugin
        now = time.time()
        failed_at = cls._jwks_failed_at.get(plugin)
        if failed_at is not None and now - failed_at < cls._JWKS_FAILURE_COOLDOWN:
            if is_log_active():
                logger.info(
                    f"_decode_token: JWKS for plugin='{plugin}' in failure cooldown "
                    f"({now - failed_at:.0f}s/{cls._JWKS_FAILURE_COOLDOWN}s), "
                    f"skipping fetch"
                )
            return None
        try:
            signing_key = self._get_jwks_client(plugin=plugin).get_signing_key_from_jwt(
                token
            )
        except PyJWKClientError as exc:
            cls._jwks_failed_at[plugin] = now
            logger.info("JWKS lookup failed: %s", exc)
            return None
        except Exception as exc:
            # Network, DNS, or misconfiguration. Degrade gracefully.
            cls._jwks_failed_at[plugin] = now
            logger.warning("JWKS unreachable: %s", exc)
            return None
        # JWKS endpoint is reachable again; clear any prior failure backoff.
        cls._jwks_failed_at.pop(plugin, None)

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
            audience = os.environ.get(
                "SSO_APPS_AUDIENCE",
                os.environ.get("SSO_APPS_CLIENT_ID", "imio-apps-plone"),
            )
        if is_log_active():
            logger.info(
                f"_decode_token: (plugin {plugin}) verifying token with issuer='{issuer}', audience='{audience}'"
            )
        try:
            payload = jwt.decode(
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
            if is_log_active():
                logger.info("_decode_token: token verification successful")
            return payload
        except InvalidTokenError as exc:
            logger.info("JWT rejected: %s", exc)
            return None

    def _ensure_user_exists(self, userid, payload):
        if api.user.get(userid=userid) is not None:
            if is_log_active():
                logger.info(
                    f"_ensure_user_exists: user '{userid}' already exists, skipping creation"
                )
            return
        if is_log_active():
            logger.info(f"_ensure_user_exists: creating new user '{userid}'")
        try:
            new_user = self._create_user(userid)
        except Exception:
            logger.exception("Could not create local user for %s", userid)
            return
        # Read OIDC claim names from the JWT. Keycloak's Admin REST API uses
        # different field names (username/id/firstName/lastName), but a token
        # carries the OIDC claims preferred_username/sub/given_name/family_name.
        username = payload.get("preferred_username", "")
        email = payload.get("email", "")
        given_name = payload.get("given_name", "")
        family_name = payload.get("family_name", "")
        if username:
            if not email:
                email = f"{username}@kimug.be"
            if not given_name and not family_name:
                given_name = username
                family_name = "sso-apps"
        userinfo = {
            "username": username,
            "email": email,
            "keycloak_id": payload.get("sub", ""),
            # The parent _update_user_properties maps given_name + family_name
            # to the Plone fullname property.
            "given_name": given_name,
            "family_name": family_name,
        }

        if is_log_active():
            logger.info(
                f"_ensure_user_exists: updating user '{userid}' with userinfo={userinfo}"
            )
        try:
            self._update_user(new_user, userinfo, first_login=True)
            if is_log_active():
                logger.info(
                    f"_ensure_user_exists: user '{userid}' created and updated successfully"
                )
        except Exception as e:
            logger.error(
                "Not able to update user %s (userid=%s, userinfo=%s): %s",
                payload.get("email") or userinfo.get("email"),
                userid,
                userinfo,
                e,
            )


InitializeClass(KimugPlugin)
