from Acquisition import aq_base
from pas.plugins.kimug.controlpanel.classic import KimugControlPanelAdapter
from pas.plugins.kimug.controlpanel.classic import KimugSettingsControlPanel
from pas.plugins.kimug.controlpanel.classic import KimugSSOAppsSettingsForm
from plone import api


class TestControlPanelAdapter:
    def test_adapter_defaults_to_oidc_plugin(self, portal):
        """Without a plugin_id the adapter wraps the main ``oidc`` plugin."""
        adapter = KimugControlPanelAdapter(portal)
        assert adapter.plugin_id == "oidc"
        assert aq_base(adapter.settings) is aq_base(portal.acl_users["oidc"])

    def test_adapter_targets_sso_apps_plugin(self, portal):
        """With plugin_id the adapter wraps the ``oidc_sso_apps`` plugin."""
        adapter = KimugControlPanelAdapter(portal, plugin_id="oidc_sso_apps")
        assert adapter.plugin_id == "oidc_sso_apps"
        assert aq_base(adapter.settings) is aq_base(portal.acl_users["oidc_sso_apps"])

    def test_adapter_writes_sso_apps_settings(self, portal):
        """Setting issuer/client_id/client_secret persists on the plugin."""
        adapter = KimugControlPanelAdapter(portal, plugin_id="oidc_sso_apps")
        adapter.issuer = "https://example.org/realms/sso-apps"
        adapter.client_id = "my-client"
        adapter.client_secret = "my-secret"  # nosec B105

        plugin = portal.acl_users["oidc_sso_apps"]
        assert plugin.issuer == "https://example.org/realms/sso-apps"
        assert plugin.client_id == "my-client"
        assert plugin.client_secret == "my-secret"  # nosec B105

    def test_adapter_writes_municipality_groups(self, portal):
        """Setting municipality_groups through the adapter persists on the plugin."""
        adapter = KimugControlPanelAdapter(portal, plugin_id="oidc_sso_apps")
        adapter.municipality_groups = ("pl_belleville_ac", "pl_another_ic")

        plugin = portal.acl_users["oidc_sso_apps"]
        assert plugin.getProperty("municipality_groups") == (
            "pl_belleville_ac",
            "pl_another_ic",
        )


class TestSSOAppsSettingsForm:
    def test_form_targets_sso_apps_plugin(self, portal, http_request):
        form = KimugSSOAppsSettingsForm(portal, http_request)
        content = form.getContent()
        assert content.plugin_id == "oidc_sso_apps"

    def test_form_has_distinct_prefix(self, portal, http_request):
        """A distinct prefix avoids widget/button collisions with the oidc form."""
        form = KimugSSOAppsSettingsForm(portal, http_request)
        assert form.prefix == "sso_apps"

    def test_apply_changes_writes_to_plugin(self, portal, http_request):
        form = KimugSSOAppsSettingsForm(portal, http_request)
        form.applyChanges(
            {
                "issuer": "https://example.org/realms/sso-apps",
                "client_id": "apps-client",
                "client_secret": "apps-secret",  # nosec B105
                "municipality_groups": ["pl_belleville_ac"],
            }
        )
        plugin = portal.acl_users["oidc_sso_apps"]
        assert plugin.issuer == "https://example.org/realms/sso-apps"
        assert plugin.client_id == "apps-client"
        assert plugin.client_secret == "apps-secret"  # nosec B105
        assert list(plugin.getProperty("municipality_groups")) == ["pl_belleville_ac"]


class TestControlPanelView:
    def test_renders_sso_apps_form_fragment(self, portal, http_request):
        with api.env.adopt_roles(["Manager"]):
            view = portal.restrictedTraverse("@@kimug-controlpanel")
            view.update()
            contents = view.sso_apps_contents
        # The SSO Apps form must render as a bare wrapped-form fragment, not a
        # full standalone page (no main_template chrome / duplicated footer).
        assert 'name="sso_apps' in contents
        assert "</body>" not in contents

    def test_debug_mode_reflects_registry_record(self, portal, http_request):
        api.portal.set_registry_record("pas.plugins.kimug.log", True)
        view = KimugSettingsControlPanel(portal, http_request)
        assert view.debug_mode() is True
        api.portal.set_registry_record("pas.plugins.kimug.log", False)
        assert view.debug_mode() is False


class TestToggleDebugMode:
    RECORD = "pas.plugins.kimug.log"

    def test_toggle_flips_registry_record(self, portal, http_request):
        api.portal.set_registry_record(self.RECORD, False)
        with api.env.adopt_roles(["Manager"]):
            view = portal.restrictedTraverse("@@toggle_debug_mode")
            view()
        assert api.portal.get_registry_record(self.RECORD) is True

    def test_toggle_is_reversible(self, portal, http_request):
        api.portal.set_registry_record(self.RECORD, True)
        with api.env.adopt_roles(["Manager"]):
            view = portal.restrictedTraverse("@@toggle_debug_mode")
            view()
        assert api.portal.get_registry_record(self.RECORD) is False
