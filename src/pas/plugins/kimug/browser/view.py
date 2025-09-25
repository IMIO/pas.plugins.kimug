from oic import rndstr
from oic.oic.message import IdToken
from pas.plugins.kimug.utils import add_keycloak_users_to_plone
from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import get_keycloak_users_from_oidc
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from pas.plugins.kimug.utils import set_oidc_settings
from pas.plugins.oidc import _
from pas.plugins.oidc import plugins
from pas.plugins.oidc import utils
from pas.plugins.oidc.browser.view import LoginView
from pas.plugins.oidc.plugins import OAuth2ConnectionException
from pas.plugins.oidc.session import Session
from plone import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zExceptions import Unauthorized

import logging


logger = logging.getLogger("pas.plugins.kimug.view")


class MigrationView(BrowserView):
    def __call__(self):
        keycloak_users = get_keycloak_users()
        plone_users = api.user.get_users()
        migrate_plone_user_id_to_keycloak_user_id(
            plone_users,
            keycloak_users,
        )
        return self.index()


class SetOidcSettingsView(BrowserView):
    def __call__(self):
        set_oidc_settings(self.context)
        api.portal.show_message("OIDC settings configured successfully", self.request)
        logger.info("OIDC settings configured successfully")
        referer = self.request.get("HTTP_REFERER")
        if referer:
            self.request.response.redirect(referer)
        else:
            self.request.response.redirect(self.context.absolute_url())


class KeycloakUsersView(BrowserView):
    # If you want to define a template here, please remove the template attribute from
    # the configure.zcml registration of this view.
    # template = ViewPageTemplateFile('my_view.pt')
    index = ViewPageTemplateFile("users.pt")

    def __call__(self):
        keycloak_users = get_keycloak_users_from_oidc()
        added_users = add_keycloak_users_to_plone(keycloak_users)
        api.portal.show_message(f"{added_users} Keycloak users imported", self.request)
        return self.index()


class KimugLoginView(LoginView):
    def initialize_session(self, plugin: plugins.OIDCPlugin, request) -> Session:
        """Initialize a Session."""
        use_session_data_manager: bool = plugin.getProperty("use_session_data_manager")
        use_pkce: bool = plugin.getProperty("use_pkce")
        session = Session(request, use_session_data_manager)
        # state is used to keep track of responses to outstanding requests (state).
        # nonce is a string value used to associate a Client session with an ID Token, and
        # to mitigate replay attacks.
        session.set("state", rndstr())
        session.set("nonce", rndstr())
        # came_from = request.get("came_from")
        came_from = request.get("HTTP_REFERER")
        if came_from:
            session.set("came_from", came_from)
        if use_pkce:
            session.set("verifier", rndstr(128))
        return session

    def __call__(self):
        session = self.initialize_session(self.context, self.request)
        args = utils.authorization_flow_args(self.context, session)
        error_msg = ""
        try:
            client = self.context.get_oauth2_client()
        except OAuth2ConnectionException:
            client = None
            error_msg = _("There was an error getting the oauth2 client.")
        if client:
            try:
                auth_req = client.construct_AuthorizationRequest(request_args=args)
                login_url = auth_req.request(client.authorization_endpoint)
            except Exception as e:
                logger.error(e)
                error_msg = _(
                    "There was an error during the login process. Please try again."
                )
            else:
                self.request.response.setHeader(
                    "Cache-Control", "no-cache, must-revalidate"
                )
                self.request.response.redirect(login_url)

        if error_msg:
            api.portal.show_message(error_msg)
            redirect_location = self._internal_redirect_location(session)
            self.request.response.redirect(redirect_location)
        return


class CallbackView(BrowserView):
    def __call__(self):
        session = utils.load_existing_session(self.context, self.request)
        client = self.context.get_oauth2_client()
        qs = self.request.environ["QUERY_STRING"]
        args, state = utils.parse_authorization_response(
            self.context, qs, client, session
        )
        # came_from = session.get("came_from")
        method = self.context.getProperty("userinfo_endpoint_method", "POST")
        if self.context.getProperty("use_modified_openid_schema"):
            IdToken.c_param.update(
                {
                    "email_verified": utils.SINGLE_OPTIONAL_BOOLEAN_AS_STRING,
                    "phone_number_verified": utils.SINGLE_OPTIONAL_BOOLEAN_AS_STRING,
                }
            )

        # The response you get back is an instance of an AccessTokenResponse
        # or again possibly an ErrorResponse instance.
        user_info = utils.get_user_info(client, state, args, method)
        if user_info:
            self.context.rememberIdentity(user_info)
            self.request.response.setHeader(
                "Cache-Control", "no-cache, must-revalidate"
            )
            return_url = utils.process_came_from(session, session.get("came_from"))
            self.request.response.redirect(return_url)
        else:
            raise Unauthorized()
