from pas.plugins.kimug.utils import add_keycloak_users_to_plone
from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import get_keycloak_users_from_oidc
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from pas.plugins.kimug.utils import set_oidc_settings
from plone import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

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
