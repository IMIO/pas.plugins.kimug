from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from pas.plugins.kimug.utils import set_oidc_settings
from plone import api
from Products.Five.browser import BrowserView

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
        self.request.response.redirect(self.context.absolute_url())
