from pas.plugins.kimug import utils
from pas.plugins.kimug.utils import is_log_active
from plone import api
from unittest.mock import MagicMock
from unittest.mock import patch
from ZODB.POSException import ConflictError
from zope.annotation.interfaces import IAnnotations

import os
import pytest
import requests


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


class TestGetKeycloakUsersFromOidcSsoApps:
    def _configure_plugin(self):
        plugin = utils.get_plugin("oidc_sso_apps")
        plugin.issuer = "https://sso.example.com/realms/sso-apps"
        plugin.client_id = "test-client"
        plugin.client_secret = "test-secret"
        return plugin

    def _mock_response(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def test_returns_users(self, portal):
        """Happy path: users from the access group are returned with correct fields."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        members = [
            {
                "id": "uid-1",
                "username": "alice",
                "email": "alice@example.com",
                "firstName": "Alice",
                "lastName": "Smith",
            }
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert result == [
            {
                "username": "alice",
                "email": "alice@example.com",
                "keycloak_id": "uid-1",
                "firstName": "Alice",
                "lastName": "Smith",
            }
        ]

    def test_filters_users_without_username(self, portal):
        """Users missing username are excluded; users missing email or names get defaults."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        members = [
            {"id": "uid-1", "username": "alice", "email": "alice@example.com"},
            {"id": "uid-2", "username": "", "email": "no-username@example.com"},
            {"id": "uid-3", "username": "no-email", "email": ""},
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert len(result) == 2
        usernames = [u["username"] for u in result]
        assert "alice" in usernames
        assert "no-email" in usernames
        assert "" not in usernames

    def test_missing_email_is_filled_with_kimug_domain(self, portal):
        """A user with no email gets email auto-filled as {username}@kimug.be."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        members = [
            {
                "id": "uid-1",
                "username": "bob",
                "email": "",
                "firstName": "Bob",
                "lastName": "Smith",
            }
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert len(result) == 1
        assert result[0]["email"] == "bob@kimug.be"

    def test_missing_names_are_filled_with_username_and_sso_apps(self, portal):
        """A user with no firstName and no lastName gets them filled from username / 'sso-apps'."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        members = [
            {
                "id": "uid-1",
                "username": "carol",
                "email": "carol@example.com",
                "firstName": "",
                "lastName": "",
            }
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert len(result) == 1
        assert result[0]["firstName"] == "carol"
        assert result[0]["lastName"] == "sso-apps"

    def test_partial_name_is_not_overridden(self, portal):
        """A user with only one name field missing is not overridden (both must be absent)."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        members = [
            {
                "id": "uid-1",
                "username": "dave",
                "email": "dave@example.com",
                "firstName": "Dave",
                "lastName": "",
            }
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert len(result) == 1
        assert result[0]["firstName"] == "Dave"
        assert result[0]["lastName"] == ""

    def test_custom_access_group_env_var(self, portal):
        """SSO_APPS_ACCESS_GROUP env var overrides the default access group name."""
        self._configure_plugin()
        groups = [
            {"id": "grp-default", "name": "access_imio-apps-kimug"},
            {"id": "grp-custom", "name": "my-custom-group"},
        ]
        members = [
            {
                "id": "uid-1",
                "username": "bob",
                "email": "bob@example.com",
                "firstName": "Bob",
                "lastName": "Jones",
            }
        ]
        with patch.dict(os.environ, {"SSO_APPS_ACCESS_GROUP": "my-custom-group"}):
            with patch(
                "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
            ):
                with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                    mock_get.side_effect = [
                        self._mock_response(groups),
                        self._mock_response(members),
                    ]
                    result = utils.get_keycloak_users_from_oidc_sso_apps()

        assert len(result) == 1
        assert result[0]["username"] == "bob"
        members_url = mock_get.call_args_list[1].kwargs["url"]
        assert "grp-custom" in members_url

    def test_plugin_not_found_returns_empty_list(self, portal):
        """If oidc_sso_apps plugin is not found the function returns []."""
        with patch("pas.plugins.kimug.utils.get_plugin", return_value=None):
            result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []

    def test_no_issuer_returns_empty_list(self, portal):
        """If plugin.issuer is empty the function returns []."""
        plugin = self._configure_plugin()
        plugin.issuer = ""
        result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []

    def test_invalid_issuer_returns_empty_list(self, portal):
        """If plugin.issuer cannot be parsed (no scheme/netloc) the function returns []."""
        plugin = self._configure_plugin()
        plugin.issuer = "not-a-valid-url"
        result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []

    def test_no_access_token_returns_empty_list(self, portal):
        """If get_client_access_token returns None the function returns []."""
        self._configure_plugin()
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value=None
        ):
            result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []

    def test_request_exception_on_groups_fetch_propagates(self, portal):
        """A RequestException on the groups fetch propagates (call is outside try/except)."""
        self._configure_plugin()
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = requests.exceptions.RequestException(
                    "groups error"
                )
                with pytest.raises(requests.exceptions.RequestException):
                    utils.get_keycloak_users_from_oidc_sso_apps()

    def test_request_exception_on_members_fetch_returns_empty_list(self, portal):
        """A RequestException on the members fetch is caught and [] is returned."""
        self._configure_plugin()
        groups = [{"id": "grp-1", "name": "access_imio-apps-kimug"}]
        mock_members_resp = MagicMock()
        mock_members_resp.raise_for_status.side_effect = (
            requests.exceptions.RequestException("members error")
        )
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    mock_members_resp,
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []


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


class TestIsLogActive:
    def test_is_log_active_default_false(self, portal):
        """is_log_active returns False when registry record is set to False (default)."""
        assert is_log_active() is False

    def test_is_log_active_true(self, portal):
        """is_log_active returns True when registry record is set to True."""
        api.portal.set_registry_record("pas.plugins.kimug.log", True)
        assert is_log_active() is True
        api.portal.set_registry_record("pas.plugins.kimug.log", False)
