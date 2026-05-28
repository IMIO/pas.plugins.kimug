from pas.plugins.kimug import utils
from plone import api
from unittest.mock import patch
from ZODB.POSException import ConflictError
from zope.annotation.interfaces import IAnnotations

import os


class TestUtils:
    def test_toggle_authentication_plugins(self, portal):
        """Test toggle authentication plugins methods."""

        annotations = IAnnotations(api.portal.get())

        # 1. Typical scenario: disable and enable authentication plugins
        acl_users = api.portal.get_tool("acl_users")
        all_plugins = acl_users.plugins.getAllPlugins(
            plugin_type="IAuthenticationPlugin"
        )

        initially_enabled_plugins = all_plugins.get("active")
        # 1.1 There should be some authentication plugins.
        assert len(initially_enabled_plugins) > 0

        # 1.2 Disable authentication plugins
        disabled_plugins = utils.disable_authentication_plugins()

        # 1.3 Disabled plugins should be the same as enabled plugins.
        assert disabled_plugins == list(initially_enabled_plugins)

        all_plugins = acl_users.plugins.getAllPlugins(
            plugin_type="IAuthenticationPlugin"
        )

        # 1.4 All authentication plugins should now be disabled.
        assert len(all_plugins.get("active")) == 0

        # 1.5 Enable the authentication plugins back
        utils.enable_authentication_plugins()

        all_plugins = acl_users.plugins.getAllPlugins(
            plugin_type="IAuthenticationPlugin"
        )

        # 1.6 All authentication plugins should be enabled again.
        assert all_plugins.get("active") == initially_enabled_plugins
        assert annotations.get("pas.plugins.kimug.disabled_plugins") == []

        # 2. No authentication plugins to disable
        disabled_plugins = utils.disable_authentication_plugins()
        assert annotations.get("pas.plugins.kimug.disabled_plugins") == disabled_plugins

        # 2.1 Disable again, should return an empty tuple
        # annotation should be the same as before
        assert utils.disable_authentication_plugins() == []
        assert annotations.get("pas.plugins.kimug.disabled_plugins") == disabled_plugins

        # 3. Try do enable authentication plugins, but no plugins were disabled
        utils.enable_authentication_plugins()
        assert annotations.get("pas.plugins.kimug.disabled_plugins") == []
        all_plugins = acl_users.plugins.getAllPlugins(
            plugin_type="IAuthenticationPlugin"
        )
        assert all_plugins.get("active") == initially_enabled_plugins

        utils.enable_authentication_plugins()
        all_plugins = acl_users.plugins.getAllPlugins(
            plugin_type="IAuthenticationPlugin"
        )
        # 3.1 All authentication plugins should still be enabled.
        assert all_plugins.get("active") == initially_enabled_plugins

    def test_get_plugin_with_sso_apps_id(self, portal):
        """get_plugin('oidc_sso_apps') should return the oidc_sso_apps plugin."""
        plugin = utils.get_plugin("oidc_sso_apps")
        assert plugin is not None
        assert plugin.meta_type == "Kimug Plugin"

    def test_set_allowed_groups(self, portal):
        """Test set_allowed_groups method."""

        oidc = utils.get_plugin()

        # 1. No environment variable set: allowed groups should not change
        current_allowed_groups = oidc.allowed_groups

        os.environ.pop("keycloak_allowed_groups", None)

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == current_allowed_groups

        # 2. Typical scenario: set allowed groups from environment variable

        os.environ["keycloak_allowed_groups"] = "[group1, group2, group3]"

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == ("group1", "group2", "group3")

        # 3. Empty allowed groups from environment variable

        os.environ["keycloak_allowed_groups"] = "[]"

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == ("",)

        # 4. Another format of allowed groups from environment variable (no brackets)

        os.environ["keycloak_allowed_groups"] = "group 1"

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == ("group 1",)

        # 5. Another format of allowed groups from environment variable (special chars)

        os.environ[
            "keycloak_allowed_groups"
        ] = "[group.1 is - the first!, group_2@second]"

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == ("group.1 is - the first!", "group_2@second")

        os.environ["keycloak_allowed_groups"] = "group.1 is - the first!"

        utils._set_allowed_groups(oidc)

        assert oidc.allowed_groups == ("group.1 is - the first!",)


class TestSetOidcSettings:
    def test_conflict_error_is_handled(self, portal):
        """ConflictError on commit must be caught and transaction aborted — no exception raised."""
        with patch("pas.plugins.kimug.utils.transaction") as mock_txn:
            mock_txn.commit.side_effect = ConflictError()
            utils.set_oidc_settings(None)
            mock_txn.abort.assert_called_once()

    def test_settings_are_applied(self, portal):
        """set_oidc_settings should apply environment values to the OIDC plugin."""
        with patch.dict(os.environ, {"keycloak_client_id": "my-client"}):
            with patch("pas.plugins.kimug.utils.transaction"):
                utils.set_oidc_settings(None)
        oidc = utils.get_plugin()
        assert oidc.client_id == "my-client"

    def test_sso_apps_settings_are_applied(self, portal):
        """set_oidc_settings should configure the oidc_sso_apps plugin from SSO_APPS_* env vars."""
        env = {
            "SSO_APPS_CLIENT_ID": "test-client",
            "SSO_APPS_CLIENT_SECRET": "test-secret",
            "SSO_APPS_URL": "https://sso.example.com/realms/sso-apps",
        }
        with patch.dict(os.environ, env):
            with patch("pas.plugins.kimug.utils.transaction"):
                utils.set_oidc_settings(None)
        plugin = utils.get_plugin("oidc_sso_apps")
        assert plugin.client_id == "test-client"
        assert plugin.client_secret == "test-secret"
        assert plugin.issuer == "https://sso.example.com/realms/sso-apps"
