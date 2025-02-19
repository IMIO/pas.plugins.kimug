from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from pas.plugins.kimug.interfaces import IKimugPlugin
from pas.plugins.oidc.plugins import OIDCPlugin
from Products.CMFCore.permissions import ManagePortal
from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from Products.PluggableAuthService.interfaces import plugins as pas_interfaces
from zope.interface import implementer


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
)
class KimugPlugin(OIDCPlugin):
    security = ClassSecurityInfo()
    meta_type = "Kimug Plugin"
    # BasePlugin.manage_options
    # manage_options = (
    #     {"label": "iMio Users", "action": "manage_kimugplugin"},
    # ) + OIDCPlugin.manage_options
    # security.declareProtected(ManagePortal, "manage_kimugplugin")
    # manage_kimugplugin = PageTemplateFile(
    #     "zmi", globals(), __name__="manage_kimugplugin"
    # )

    # Tell PAS not to swallow our exceptions
    _dont_swallow_my_exceptions = True

    # def __init__(self, id, title=None):
    #     __import__("ipdb").set_trace()
    #     self._setId(id)
    #     self.title = title

    @security.private
    def getRolesForPrincipal(self, user, request=None):
        """Fullfill RolesPlugin requirements"""
        pass


InitializeClass(KimugPlugin)
