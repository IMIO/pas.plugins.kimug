from pas.plugins.kimug.plugin import KimugPlugin
from pas.plugins.kimug.utils import clean_authentic_users
from pas.plugins.kimug.utils import get_keycloak_users
from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
from pas.plugins.kimug.utils import realm_exists
from pas.plugins.kimug.utils import set_oidc_settings
from pas.plugins.kimug.utils import varenvs_exist
from plone import api
from Products.CMFPlone.interfaces import INonInstallable
from Products.PluggableAuthService.interfaces.plugins import IChallengePlugin
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


def _add_plugin(pas, pluginid="oidc", title="OIDC", challenge=True):
    if pluginid in pas.objectIds():
        return pluginid + " already installed."
    plugin = KimugPlugin(pluginid, title=title)
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
    if not challenge:
        # This plugin only validates Bearer tokens; it must not challenge
        # browser users (that would redirect to the wrong login). Leave the
        # interactive login challenge to the "oidc" plugin.
        active = [x[0] for x in pas.plugins.listPlugins(IChallengePlugin)]
        if pluginid in active:
            pas.plugins.deactivatePlugin(IChallengePlugin, pluginid)


def post_install(context):
    """Post install script"""
    # Add oidc to acl_users
    _add_plugin(api.portal.get_tool("acl_users"), pluginid="oidc", title="OIDC")
    # Add sso-apps to acl_users
    _add_plugin(
        api.portal.get_tool("acl_users"),
        pluginid="oidc_sso_apps",
        title="OIDC SSO Apps",
        challenge=False,
    )

    set_oidc_settings(context)
    if varenvs_exist():
        keycloak_realm = os.environ.get("keycloak_realm", "")
        if realm_exists(keycloak_realm):
            kc_users = get_keycloak_users()
            migrate_plone_user_id_to_keycloak_user_id(
                api.user.get_users(),
                kc_users,
            )
            clean_authentic_users()
        else:
            logger.error(f"Keycloak realm '{keycloak_realm}' does not exist.")
