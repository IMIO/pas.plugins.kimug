from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from pas.plugins.kimug.interfaces import IKimugPlugin
from pas.plugins.oidc.plugins import OIDCPlugin
from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from Products.PluggableAuthService.interfaces import plugins as pas_interfaces
from zope.interface import implementer

import jwt
import os


# from jwt.algorithms import RSAAlgorithm
# import requests


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

    @security.private
    def getRolesForPrincipal(self, user, request=None):
        """Fulfill RolesPlugin requirements"""
        app_id = os.environ.get("application_id", "smartweb")
        roles = ["Member"]
        if app_id in user.getGroups():
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
        """credentials -> (userid, login)

        - 'credentials' will be a mapping, as returned by IExtractionPlugin.
        - Return a  tuple consisting of user ID (which may be different
          from the login name) and login
        - If the credentials cannot be authenticated, return None.
        """
        token = credentials.get("token", None)
        if token:
            payload = self._decode_token(token)
            return payload.get("sub"), payload.get("email")

    def _decode_token(self, token):
        # Fetch JWKS from Keycloak
        # keycloak_url = os.environ.get("keycloak_url")
        # realm = os.environ.get("keycloak_realm")
        # jwks_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/certs"
        # jwks = requests.get(jwks_url).json()

        # Extract public key
        # public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])

        # Decode & verify
        # __import__("ipdb").set_trace()
        # decoded = jwt.decode(
        #     token, key=public_key, algorithms=["RS256"], audience="account"
        # )

        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded


InitializeClass(KimugPlugin)
