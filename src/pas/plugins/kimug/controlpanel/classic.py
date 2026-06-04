from Acquisition import aq_inner
from pas.plugins.kimug import _
from pas.plugins.kimug import PLUGIN_ID
from pas.plugins.kimug import SSO_APPS_PLUGIN_ID
from pas.plugins.kimug.interfaces import IKimugSettings
from pas.plugins.kimug.interfaces import IKimugSSOAppsSettings
from pas.plugins.kimug.utils import check_keycloak_settings
from plone import api
from plone.app.registry.browser import controlpanel
from plone.base.interfaces import IPloneSiteRoot
from plone.z3cform.interfaces import IWrappedForm
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from z3c.form.interfaces import DISPLAY_MODE
from z3c.form.interfaces import ISubForm
from zope.component import adapter
from zope.interface import alsoProvides
from zope.interface import implementer


@adapter(IPloneSiteRoot)
@implementer(IKimugSettings, IKimugSSOAppsSettings)
class KimugControlPanelAdapter:
    propertymap = None

    def __init__(self, context, plugin_id=PLUGIN_ID):
        self.context = context
        self.plugin_id = plugin_id
        self.portal = api.portal.get()
        self.encoding = "utf-8"
        self.settings = self.portal.acl_users[plugin_id]
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
    enable_autofocus = False

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


class KimugSSOAppsSettingsForm(controlpanel.RegistryEditForm):
    schema = IKimugSSOAppsSettings
    schema_prefix = "kimug_sso_apps"
    prefix = "sso_apps"
    label = _("SSO Apps Plugin Settings (oidc_sso_apps)")
    description = ""
    enable_autofocus = False

    def getContent(self):
        portal = api.portal.get()
        return KimugControlPanelAdapter(portal, plugin_id=SSO_APPS_PLUGIN_ID)

    def updateWidgets(self):
        super().updateWidgets()
        pmap = self.getContent().propertymap
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
                changes.setdefault(IKimugSSOAppsSettings, []).append(name)
        return changes


class KimugSettingsControlPanel(controlpanel.ControlPanelFormWrapper):
    form = KimugSettingsForm
    index = ViewPageTemplateFile("controlpanel.pt")
    sso_apps_contents = ""

    def update(self):
        super().update()
        form = KimugSSOAppsSettingsForm(aq_inner(self.context), self.request)
        form.__name__ = self.__name__
        if not ISubForm.providedBy(form):
            alsoProvides(form, IWrappedForm)
        form.update()
        if self.request.response.getStatus() in (302, 303):
            self.sso_apps_contents = ""
            return
        self.sso_apps_contents = form.render()

    def debug_mode(self):
        return api.portal.get_registry_record("pas.plugins.kimug.log", default=False)

    def checkSettings(self, plugin="oidc"):
        if not check_keycloak_settings(plugin):
            if plugin == "oidc":
                return '<div class="alert alert-danger" role="alert">{}</div>'.format(
                    _(
                        "There is a problem with the Keycloak settings for SSO (plugin oidc). "
                        "Please check the Issuer URL, client ID, client secret and redirect uri"
                    )
                )
            elif plugin == "oidc_sso_apps":
                return '<div class="alert alert-danger" role="alert">{}</div>'.format(
                    _(
                        "There is a problem with the Keycloak settings for SSO Apps (plugin oidc_sso_apps). "
                        "Please check the Issuer URL, client ID and client secret"
                    )
                )
        elif plugin == "oidc":
            return '<div class="alert alert-success" role="alert">{}</div>'.format(
                _(
                    "Keycloak settings (issuer url, client id, client secret and redirect_uri) are correct."
                )
            )
        elif plugin == "oidc_sso_apps":
            return '<div class="alert alert-success" role="alert">{}</div>'.format(
                _(
                    "Keycloak settings for SSO Apps (issuer url, client id, client secret) are correct."
                )
            )
