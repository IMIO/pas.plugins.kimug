from pas.plugins.kimug.plugin import KimugPlugin

# from pas.plugins.kimug.utils import remove_authentic_plugin
from pas.plugins.kimug.utils import clean_authentic_users
from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from pas.plugins.kimug.utils import realm_exists
from pas.plugins.kimug.utils import varenvs_exist
from pas.plugins.kimug.utils import remove_authentic_plugin
from pas.plugins.kimug.utils import set_oidc_settings
from plone import api
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

import logging
import os


logger = logging.getLogger("pas.plugins.kimug.utils")


@implementer(INonInstallable)
class HiddenProfiles:
    def getNonInstallableProfiles(self):
        """Hide uninstall profile from site-creation and quickinstaller."""
        return [
            "pas.plugins.kimug:default",
            "pas.plugins.kimug:uninstall",
            "pas.plugins.oidc:default",
        ]


def _add_plugin(pas, pluginid="oidc"):
    if pluginid in pas.objectIds():
        return pluginid + " already installed."
    plugin = KimugPlugin(pluginid, title="OIDC")
    pas._setObject(pluginid, plugin)
    plugin = pas[plugin.getId()]  # get plugin acquisition wrapped!
    for info in pas.plugins.listPluginTypeInfo():
        interface = info["interface"]
        if not interface.providedBy(plugin):
            continue
        pas.plugins.activatePlugin(interface, plugin.getId())
        pas.plugins.movePluginsDown(
            interface, [x[0] for x in pas.plugins.listPlugins(interface)[:-1]]
        )


def post_install(context):
    """Post install script"""
    _add_plugin(api.portal.get_tool("acl_users"))

    set_oidc_settings(context)
    if varenvs_exist():
        keycloak_realm = os.environ.get("keycloak_realm", "")
        keycloak_realm = os.environ.get("keycloak_realm", "")
        if realm_exists(keycloak_realm):
            kc_users = get_keycloak_users()
            migrate_plone_user_id_to_keycloak_user_id(
                api.user.get_users(),
                kc_users,
            )
            clean_authentic_users()
            # remove_authentic_plugin()
        else:
            logger.error(f"Keycloak realm '{keycloak_realm}' does not exist.")
