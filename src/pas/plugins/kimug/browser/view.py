from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from plone import api
from Products.Five.browser import BrowserView

import logging


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
        keycloak_users = get_keycloak_users()
        plone_users = api.user.get_users()
        migrate_plone_user_id_to_keycloak_user_id(
            plone_users,
            keycloak_users,
        )
        return self.index()
