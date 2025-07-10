from pas.plugins.kimug import utils
from plone import api
from zope.annotation.interfaces import IAnnotations

import os


class TestUtils:
    def test_sanitize_redirect_uris(self):
        """Test sanitize_redirect_uris function."""

        good_sanitized_uris = (
            "http://url1",
            "http://url2",
            "http://url3",
        )

        redirect_uris = "('http://url1', 'http://url2', 'http://url3')"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = '("http://url1", "http://url2", "http://url3")'
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "['http://url1', 'http://url2', 'http://url3']"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = '["http://url1", "http://url2", "http://url3"]'
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "[http://url1, http://url2, http://url3]"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "something else"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == ()

    def test_get_redirect_uris(self):
        """Test get_redirect_uris function."""

        current_redirect_uris = ()

        # 1 : no values set on oidc settings

        # Test with no environment variable set
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == ("http://localhost:8080/Plone/acl_users/oidc/callback",)

        # set WEBSITE_HOSTNAME
        os.environ["WEBSITE_HOSTNAME"] = "kimug.imio.be"
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)

        # set keycloak_redirect_uris
        os.environ["keycloak_redirect_uris"] = "['http://url1', 'http://url2']"
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == (
            "http://url1",
            "http://url2",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 2 : values set on oidc settings

        redirect_uris_from_oidc_settings = (
            "http://url1",
            "http://url2",
            "http://url3",
        )

        os.environ.pop("WEBSITE_HOSTNAME", None)
        os.environ.pop("keycloak_redirect_uris", None)

        # Test with no environment variable set
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "http://localhost:8080/Plone/acl_users/oidc/callback",
        )
        # set WEBSITE_HOSTNAME
        os.environ["WEBSITE_HOSTNAME"] = "kimug.imio.be"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "https://kimug.imio.be/acl_users/oidc/callback",
        )
        # set keycloak_redirect_uris
        os.environ["keycloak_redirect_uris"] = "['http://url4', 'http://url5']"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "http://url4",
            "http://url5",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 3 : from preprod to prod

        os.environ["WEBSITE_HOSTNAME"] = "kimug.imio.be"
        os.environ.pop("keycloak_redirect_uris", None)
        redirect_uris_from_oidc_settings = (
            "https://kimug.preprod.imio.be/acl_users/oidc/callback",
        )
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)

        os.environ["keycloak_redirect_uris"] = "[http://url1, http://url2]"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == (
            "http://url1",
            "http://url2",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 4 : uris already in the oidc settings

        os.environ["WEBSITE_HOSTNAME"] = "kimug.imio.be"
        os.environ[
            "keycloak_redirect_uris"
        ] = "('https://kimug.imio.be/acl_users/oidc/callback',)"
        redirect_uris_from_oidc_settings = (
            "https://kimug.imio.be/acl_users/oidc/callback",
        )
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)

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
