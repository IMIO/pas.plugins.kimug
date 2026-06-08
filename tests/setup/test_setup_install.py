from pas.plugins.kimug import PACKAGE_NAME


class TestSetupInstall:
    def test_addon_installed(self, installer):
        """Test if pas.plugins.kimug is installed."""
        assert installer.is_product_installed(PACKAGE_NAME) is True

    def test_browserlayer(self, browser_layers):
        """Test that IBrowserLayer is registered."""
        from pas.plugins.kimug.interfaces import IBrowserLayer
        from pas.plugins.oidc.interfaces import IPasPluginsOidcLayer

        assert IBrowserLayer in browser_layers
        assert IPasPluginsOidcLayer not in browser_layers

    def test_latest_version(self, profile_last_version):
        """Test latest version of default profile."""
        assert profile_last_version(f"{PACKAGE_NAME}:default") == "1005"

    def test_acl_users_plugin(self, portal):
        """Test active plugin of acl_users."""
        pas = portal.acl_users
        oidc = portal.acl_users.oidc
        for info in pas.plugins.listPluginTypeInfo():
            interface = info["interface"]
            if info["id"] in ["IChallengePlugin", "IRolesPlugin"]:
                assert interface.providedBy(oidc)

    def test_oidc_sso_apps_plugin_installed(self, portal):
        """oidc_sso_apps plugin should be installed in acl_users after post_install."""
        assert "oidc_sso_apps" in portal.acl_users.objectIds()

    def test_oidc_is_first_challenge_plugin(self, portal):
        """oidc must handle the login challenge; oidc_sso_apps must not challenge."""
        from Products.PluggableAuthService.interfaces.plugins import IChallengePlugin

        pas = portal.acl_users
        challenge_plugins = [p[0] for p in pas.plugins.listPlugins(IChallengePlugin)]
        assert "oidc" in challenge_plugins
        assert "oidc_sso_apps" not in challenge_plugins
        assert challenge_plugins[0] == "oidc"
