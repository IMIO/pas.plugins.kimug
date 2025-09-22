from pas.plugins.kimug import _
from pas.plugins.kimug import PLUGIN_ID
from pas.plugins.kimug.interfaces import IKimugSettings
from pas.plugins.kimug.utils import check_keycloak_settings
from plone import api
from plone.app.registry.browser import controlpanel
from plone.base.interfaces import IPloneSiteRoot
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from z3c.form.interfaces import DISPLAY_MODE
from zope.component import adapter
from zope.interface import implementer


@adapter(IPloneSiteRoot)
@implementer(IKimugSettings)
class KimugControlPanelAdapter:
    propertymap = None

    def __init__(self, context):
        self.context = context
        self.portal = api.portal.get()
        self.encoding = "utf-8"
        self.settings = self.portal.acl_users[PLUGIN_ID]
        self.propertymap = {prop["id"]: prop for prop in self.settings.propertyMap()}

    def __getattr__(self, name):
        if self.propertymap and name in self.propertymap:
            return self.settings.getProperty(name)
        else:
            raise AttributeError(f"{name} not in oidcsettings")

    def __setattr__(self, name, value):
        if self.propertymap and name in self.propertymap:
            if "w" in self.propertymap[name].get("mode", ""):
                return setattr(self.settings, name, value)
            else:
                raise TypeError(f"{name} readonly in oidcsettings")
        else:
            super().__setattr__(name, value)


class KimugSettingsForm(controlpanel.RegistryEditForm):
    schema = IKimugSettings
    schema_prefix = "kimug_admin"
    label = _("Kimug Plugin Settings")
    description = ""

    excluded_fields = [
        "use_session_data_manager",
        "create_user",
        "create_groups",
        "user_property_as_groupid",
        "create_ticket",
        "create_restapi_ticket",
        "scope",
        "use_pkce",
        "use_deprecated_redirect_uri_for_logout",
        "use_modified_openid_schema",
        "user_property_as_userid",
        "identity_domain_name",
    ]

    def getContent(self):
        portal = api.portal.get()
        return KimugControlPanelAdapter(portal)

    def updateWidgets(self):
        super().updateWidgets()
        pmap = self.getContent().propertymap
        for name in self.excluded_fields:
            if name in self.widgets:
                del self.widgets[name]
        for name, widget in self.widgets.items():
            if name in pmap:
                if "w" not in pmap[name].get("mode", ""):
                    widget.mode = DISPLAY_MODE

    def applyChanges(self, data):
        """See interfaces.IEditForm"""
        content = self.getContent()
        changes = {}
        for name in data:
            current = getattr(content, name)
            value = data[name]
            if current != value:
                setattr(content, name, value)
                changes.setdefault(IKimugSettings, []).append(name)
        return changes


class KimugSettingsControlPanel(controlpanel.ControlPanelFormWrapper):
    form = KimugSettingsForm
    index = ViewPageTemplateFile("controlpanel.pt")

    def checkSettings(self):
        if not check_keycloak_settings():
            return '<div class="alert alert-danger" role="alert">{}</div>'.format(
                _(
                    "There is a problem with the Keycloak settings. "
                    "Please check the Issuer URL, client ID, client secret and redirect_uri"
                )
            )
        else:
            return '<div class="alert alert-success" role="alert">{}</div>'.format(
                _(
                    "Keycloak settings (issuer url, client id, client secret and redirect_uri) are correct."
                )
            )
