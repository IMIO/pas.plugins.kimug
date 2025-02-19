from pas.plugins.kimug.plugin import KimugPlugin
from plone import api
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer


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
