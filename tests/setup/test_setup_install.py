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
        assert IPasPluginsOidcLayer in browser_layers

    def test_latest_version(self, profile_last_version):
        """Test latest version of default profile."""
        assert profile_last_version(f"{PACKAGE_NAME}:default") == "1000"
