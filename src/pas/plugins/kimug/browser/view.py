from pas.plugins.kimug.utils import get_admin_access_token
from pas.plugins.kimug.utils import get_plugin
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
                    # plone_user.id = keycloak_user["id"]
                    # save user to pas_plugins.oidc
                    oidc = get_plugin()
                    new_user = oidc._create_user(keycloak_user["id"])
                    userinfo = {
                        "name": plone_user.getUserName(),
                        "email": keycloak_user["email"],
                        "given_name": keycloak_user["firstName"],
                        "family_name": keycloak_user["lastName"],
                    }
                    oidc._update_user(new_user, userinfo, first_login=True)

                    # update owner
                    self.update_owner(plone_user.id, keycloak_user["id"])

                    # remove user from source_users or from pas_plugins.authentic
                    # __import__("ipdb").set_trace()
                    api.user.delete(username=plone_user.id)
                    # plone_user.reindexObject()
                    logger.info(
                        f"User {plone_user.id} migrated to Keycloak user {keycloak_user['id']}"
                    )

    def update_owner(self, plone_user_id, keycloak_user_id):
        """Update the owner of the object."""
        # get all objects owned by plone_user_id
        catalog = api.portal.get_tool("portal_catalog")
        brains = catalog(
            {
                "Creator": plone_user_id,
            }
        )
        for brain in brains:
            obj = brain.getObject()
            old_modification_date = obj.ModificationDate()
            self._change_ownership(obj, plone_user_id, keycloak_user_id)
            obj.reindexObject()
            obj.setModificationDate(old_modification_date)
            obj.reindexObject(idxs=["modified"])

    def _change_ownership(self, obj, old_creator, new_owner):
        """Change object ownership"""

        # 1. Change object ownership
        acl_users = api.portal.get_tool("acl_users")
        user = acl_users.getUserById(new_owner)

        if user is None:
            user = self.membership.getMemberById(new_owner)
            if user is None:
                raise KeyError(
                    "Only retrievable users in this site can be made owners."
                )

        obj.changeOwnership(user)

        creators = list(obj.listCreators())
        if old_creator in creators:
            creators.remove(old_creator)
        if new_owner in creators:
            # Don't add same creator twice, but move to front
            del creators[creators.index(new_owner)]
        obj.setCreators([new_owner] + creators)
