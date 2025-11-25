from pas.plugins.kimug import utils
from plone import api
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

        assert oidc.allowed_groups == ()
