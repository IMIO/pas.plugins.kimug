from pas.plugins.kimug.utils import get_admin_access_token
from plone import api
from Products.Five.browser import BrowserView

import logging
import os
import requests


# from zope.interface import Interface
# from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


logger = logging.getLogger("collective.big.bang.expansion")

# class IMyView(Interface):
#     """Marker Interface for IMyView"""


class MigrationView(BrowserView):
    # If you want to define a template here, please remove the template attribute from
    # the configure.zcml registration of this view.
    # template = ViewPageTemplateFile('my_view.pt')

    def __call__(self):
        # your code here

        # render the template
        keycloak_users = self.get_keycloak_users()
        plone_users = api.user.get_users()
        self.migrate_plone_user_id_to_keycloak_user_id(
            plone_users,
            keycloak_users,
        )
        return self.index()

    def get_keycloak_users(self):
        """Get all keycloak users."""
        realm = os.environ.get("keycloak_realm")
        keycloak_url = os.environ.get("keycloak_url")
        keycloak_admin_user = os.environ.get("keycloak_admin_user")
        keycloak_admin_password = os.environ.get("keycloak_admin_password")
        access_token = get_admin_access_token(
            keycloak_url, keycloak_admin_user, keycloak_admin_password
        )
        # acl_users = api.portal.get_tool("acl_users")
        # oidc = acl_users.oidc
        # realm = oidc.issuer.split("/")[-1]

        url = f"{keycloak_url}admin/realms/{realm}/users"
        headers = {"Authorization": "Bearer " + access_token}
        response = requests.get(url=url, headers=headers)
        if response.status_code == 200 and response.json():
            return response.json()
        return []

    def migrate_plone_user_id_to_keycloak_user_id(self, plone_users, keycloak_users):
        """Migrate keycloak user id to plone user id."""
        for plone_user in plone_users:
            for keycloak_user in keycloak_users:
                if plone_user.getProperty("email") == keycloak_user["email"]:
                    __import__("ipdb").set_trace()
                    plone_user.id = keycloak_user["id"]
                    # plone_user.reindexObject()
                    logger.info(
                        f"User {plone_user.getProperty('username')} migrated to Keycloak user {keycloak_user['username']}"
                    )
