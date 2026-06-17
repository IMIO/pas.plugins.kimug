from pas.plugins.kimug import utils
from pas.plugins.kimug.utils import is_log_active
from plone import api
from plone.registry.interfaces import IRegistry
from unittest.mock import MagicMock
from unittest.mock import patch
from ZODB.POSException import ConflictError
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility

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

    def test_set_municipality_groups(self, portal):
        """Test _set_municipality_groups: env var -> oidc_sso_apps property."""

        oidc_sso_apps = utils.get_plugin("oidc_sso_apps")

        # 1. No environment variable set: property should not change
        oidc_sso_apps.municipality_groups = ("unchanged",)
        os.environ.pop("SSO_APPS_MUNICIPALITY_GROUPS", None)
        utils._set_municipality_groups(oidc_sso_apps)
        assert oidc_sso_apps.municipality_groups == ("unchanged",)

        # 2. Typical scenario: bracketed list from puppet
        os.environ["SSO_APPS_MUNICIPALITY_GROUPS"] = "[pl_belleville_ac, pl_another_ic]"
        utils._set_municipality_groups(oidc_sso_apps)
        assert oidc_sso_apps.municipality_groups == (
            "pl_belleville_ac",
            "pl_another_ic",
        )

        # 3. Empty list means no filtering (the key difference from allowed_groups)
        os.environ["SSO_APPS_MUNICIPALITY_GROUPS"] = "[]"
        utils._set_municipality_groups(oidc_sso_apps)
        assert oidc_sso_apps.municipality_groups == ()

        # 4. Single bare value (no brackets)
        os.environ["SSO_APPS_MUNICIPALITY_GROUPS"] = "pl_belleville_ac"
        utils._set_municipality_groups(oidc_sso_apps)
        assert oidc_sso_apps.municipality_groups == ("pl_belleville_ac",)

        os.environ.pop("SSO_APPS_MUNICIPALITY_GROUPS", None)


class TestGetKeycloakUsersFromOidcSsoApps:
    def _configure_plugin(self):
        plugin = utils.get_plugin("oidc_sso_apps")
        plugin.issuer = "https://sso.example.com/realms/sso-apps"
        plugin.client_id = "test-client"
        plugin.client_secret = "test-secret"
        # Default: no municipality filtering (reset to avoid leakage between tests).
        plugin.municipality_groups = ()
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

    def test_municipality_group_filtering_keeps_only_municipality_members(self, portal):
        """With the municipality_groups property set, only access-group members that are
        also in a Municipality group are imported."""
        plugin = self._configure_plugin()
        plugin.municipality_groups = ("pl_belleville_ac",)
        groups = [
            {"id": "grp-access", "name": "access_imio-apps-kimug"},
            {"id": "grp-municipality", "name": "pl_belleville_ac"},
        ]
        municipality_members = [{"id": "uid-1", "username": "alice"}]
        access_members = [
            {"id": "uid-1", "username": "alice", "email": "alice@example.com"},
            {"id": "uid-2", "username": "bob", "email": "bob@example.com"},
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(municipality_members),
                    self._mock_response(access_members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        usernames = [u["username"] for u in result]
        assert usernames == ["alice"]
        # The municipality members are fetched before the access-group members.
        municipality_url = mock_get.call_args_list[1].kwargs["url"]
        assert "grp-municipality" in municipality_url

    def test_municipality_group_not_found_returns_empty_list(self, portal):
        """If a configured Municipality group does not exist in the realm, no user qualifies."""
        plugin = self._configure_plugin()
        plugin.municipality_groups = ("pl_missing",)
        groups = [{"id": "grp-access", "name": "access_imio-apps-kimug"}]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [self._mock_response(groups)]
                result = utils.get_keycloak_users_from_oidc_sso_apps()
        assert result == []

    def test_multiple_municipality_groups_membership_in_either_qualifies(self, portal):
        """A user in any one of the configured Municipality groups is imported."""
        plugin = self._configure_plugin()
        plugin.municipality_groups = ("pl_belleville_ac", "pl_another_ic")
        groups = [
            {"id": "grp-access", "name": "access_imio-apps-kimug"},
            {"id": "grp-municipality1", "name": "pl_belleville_ac"},
            {"id": "grp-municipality2", "name": "pl_another_ic"},
        ]
        pl1_members = [{"id": "uid-1", "username": "alice"}]
        pl2_members = [{"id": "uid-2", "username": "bob"}]
        access_members = [
            {"id": "uid-1", "username": "alice", "email": "alice@example.com"},
            {"id": "uid-2", "username": "bob", "email": "bob@example.com"},
            {"id": "uid-3", "username": "carol", "email": "carol@example.com"},
        ]
        with patch(
            "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
        ):
            with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                mock_get.side_effect = [
                    self._mock_response(groups),
                    self._mock_response(pl1_members),
                    self._mock_response(pl2_members),
                    self._mock_response(access_members),
                ]
                result = utils.get_keycloak_users_from_oidc_sso_apps()

        usernames = sorted(u["username"] for u in result)
        assert usernames == ["alice", "bob"]


class TestMunicipalityFromGroupName:
    def test_strips_pl_prefix_and_type_suffix(self):
        assert utils._municipality_from_group_name("pl_amay-ac") == "amay"

    def test_cpas_variant_yields_same_slug_as_ac(self):
        assert utils._municipality_from_group_name("pl_amay-cpas") == "amay"

    def test_strips_leading_slash_path(self):
        assert utils._municipality_from_group_name("/pl_amay-ac") == "amay"

    def test_multi_segment_type_is_stripped(self):
        assert utils._municipality_from_group_name("pl_imio-ic-demo-client") == "imio"

    def test_non_pl_group_returns_none(self):
        assert utils._municipality_from_group_name("access_imio-apps-kimug") is None

    def test_empty_or_none_returns_none(self):
        assert utils._municipality_from_group_name("") is None
        assert utils._municipality_from_group_name(None) is None


class TestGetSsoAppsUsersWithMunicipalities:
    def _configure_plugin(self):
        plugin = utils.get_plugin("oidc_sso_apps")
        plugin.issuer = "https://sso.example.com/realms/sso-apps"
        plugin.client_id = "test-client"
        plugin.client_secret = "test-secret"
        plugin.municipality_groups = ()
        return plugin

    def _mock_response(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def _base_user(self, **overrides):
        user = {
            "username": "alice",
            "email": "alice@example.com",
            "keycloak_id": "uid-1",
            "firstName": "Alice",
            "lastName": "Smith",
        }
        user.update(overrides)
        return user

    def test_attaches_municipality(self, portal):
        """The 'pl_<municipality>-<type>' group is stripped to a municipality slug."""
        self._configure_plugin()
        base_users = [self._base_user()]
        user_groups = [
            {"id": "g1", "name": "pl_belleville-ac", "path": "/pl_belleville-ac"},
            {"id": "g2", "name": "access_imio-apps-kimug"},
        ]
        with patch(
            "pas.plugins.kimug.utils.get_keycloak_users_from_oidc_sso_apps",
            return_value=base_users,
        ):
            with patch(
                "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
            ):
                with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                    mock_get.side_effect = [self._mock_response(user_groups)]
                    result = utils.get_sso_apps_users_with_municipalities()

        assert result == [{**base_users[0], "municipalities": ["belleville"]}]

    def test_multiple_municipalities_deduplicated(self, portal):
        """A user in several 'pl_' groups gets all slugs; AC/CPAS variants of the
        same locality collapse to one slug; paths handled."""
        self._configure_plugin()
        base_users = [self._base_user(username="bob", keycloak_id="uid-2")]
        user_groups = [
            {"name": "pl_belleville-ac"},
            {"name": "/pl_another-ic"},
            {"name": "pl_belleville-cpas"},
            {"name": "some-other-group"},
        ]
        with patch(
            "pas.plugins.kimug.utils.get_keycloak_users_from_oidc_sso_apps",
            return_value=base_users,
        ):
            with patch(
                "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
            ):
                with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                    mock_get.side_effect = [self._mock_response(user_groups)]
                    result = utils.get_sso_apps_users_with_municipalities()

        assert result[0]["municipalities"] == ["belleville", "another"]

    def test_no_pl_group_yields_empty_municipalities(self, portal):
        """A user with no 'pl_' group gets an empty municipalities list."""
        self._configure_plugin()
        base_users = [self._base_user(username="carol", keycloak_id="uid-3")]
        user_groups = [{"name": "access_imio-apps-kimug"}]
        with patch(
            "pas.plugins.kimug.utils.get_keycloak_users_from_oidc_sso_apps",
            return_value=base_users,
        ):
            with patch(
                "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
            ):
                with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                    mock_get.side_effect = [self._mock_response(user_groups)]
                    result = utils.get_sso_apps_users_with_municipalities()

        assert result[0]["municipalities"] == []

    def test_no_users_returns_empty_list(self, portal):
        """If no eligible sso-apps users, return [] without further calls."""
        with patch(
            "pas.plugins.kimug.utils.get_keycloak_users_from_oidc_sso_apps",
            return_value=[],
        ):
            result = utils.get_sso_apps_users_with_municipalities()
        assert result == []

    def test_request_exception_returns_empty_list(self, portal):
        """A RequestException while fetching user groups is caught and [] returned."""
        self._configure_plugin()
        base_users = [self._base_user(username="dave", keycloak_id="uid-4")]
        with patch(
            "pas.plugins.kimug.utils.get_keycloak_users_from_oidc_sso_apps",
            return_value=base_users,
        ):
            with patch(
                "pas.plugins.kimug.utils.get_client_access_token", return_value="tok"
            ):
                with patch("pas.plugins.kimug.utils.requests.get") as mock_get:
                    mock_get.side_effect = requests.exceptions.RequestException("boom")
                    result = utils.get_sso_apps_users_with_municipalities()
        assert result == []


class TestSetSsoAppsLocalRoles:
    def _make_user(self, userid, username, email):
        return api.user.create(
            email=email,
            username=username,
            password="Secret123!",
            properties={"username": username},
        )

    def _user_dict(self, **overrides):
        user = {
            "username": "alice",
            "email": "alice@example.com",
            "keycloak_id": "uid-1",
            "firstName": "Alice",
            "lastName": "Smith",
            "municipalities": ["belleville"],
        }
        user.update(overrides)
        return user

    def test_grants_local_roles_on_matching_folder(self, portal):
        """A user with a 'belleville' municipality gets the local roles on /belleville."""
        with api.env.adopt_roles(["Manager"]):
            self._make_user("alice", "alice", "alice@example.com")
            folder = api.content.create(
                container=portal, type="Folder", id="belleville", title="Belleville"
            )
            with patch(
                "pas.plugins.kimug.utils.get_sso_apps_users_with_municipalities",
                return_value=[self._user_dict()],
            ):
                with patch("pas.plugins.kimug.utils.transaction"):
                    summary = utils.set_sso_apps_local_roles(portal)

            roles = folder.get_local_roles_for_userid("alice")
        assert set(utils.SSO_APPS_LOCAL_ROLES).issubset(set(roles))
        assert [(u, uid, loc) for (u, uid, loc) in summary["granted"]] == [
            ("alice", "alice", "belleville")
        ]
        assert summary["dry_run"] is False

    def test_dry_run_makes_no_changes(self, portal):
        """With dry_run=True the summary reports the grant but no role is set."""
        user = self._user_dict(
            username="bob", keycloak_id="uid-2", municipalities=["namur"]
        )
        with api.env.adopt_roles(["Manager"]):
            self._make_user("bob", "bob", "bob@example.com")
            folder = api.content.create(
                container=portal, type="Folder", id="namur", title="Namur"
            )
            with patch(
                "pas.plugins.kimug.utils.get_sso_apps_users_with_municipalities",
                return_value=[user],
            ):
                with patch("pas.plugins.kimug.utils.transaction") as mock_txn:
                    summary = utils.set_sso_apps_local_roles(portal, dry_run=True)

            local_roles = folder.get_local_roles_for_userid("bob")
        assert local_roles == ()
        assert summary["dry_run"] is True
        assert len(summary["granted"]) == 1
        mock_txn.commit.assert_not_called()

    def test_missing_user_and_missing_folder_are_reported(self, portal):
        """Users absent from Plone and slugs without a folder land in the summary."""
        users = [
            self._user_dict(username="carol", municipalities=["ghost-town"]),
            self._user_dict(username="ghost", keycloak_id="uid-99"),
        ]
        with api.env.adopt_roles(["Manager"]):
            self._make_user("carol", "carol", "carol@example.com")
            with patch(
                "pas.plugins.kimug.utils.get_sso_apps_users_with_municipalities",
                return_value=users,
            ):
                with patch("pas.plugins.kimug.utils.transaction"):
                    summary = utils.set_sso_apps_local_roles(portal)

        assert ("carol", "ghost-town") in summary["no_folder"]
        assert "ghost" in summary["missing_user"]
        assert summary["granted"] == []

    def test_idempotent_merges_existing_roles(self, portal):
        """An existing unrelated local role is preserved when the roles are merged."""
        user = self._user_dict(
            username="dave", keycloak_id="uid-3", municipalities=["liege"]
        )
        with api.env.adopt_roles(["Manager"]):
            self._make_user("dave", "dave", "dave@example.com")
            folder = api.content.create(
                container=portal, type="Folder", id="liege", title="Liege"
            )
            folder.manage_setLocalRoles("dave", ["Reviewer"])
            with patch(
                "pas.plugins.kimug.utils.get_sso_apps_users_with_municipalities",
                return_value=[user],
            ):
                with patch("pas.plugins.kimug.utils.transaction"):
                    utils.set_sso_apps_local_roles(portal)

            roles = set(folder.get_local_roles_for_userid("dave"))
        assert "Reviewer" in roles
        assert set(utils.SSO_APPS_LOCAL_ROLES).issubset(roles)

    def test_conflict_error_is_handled(self, portal):
        """A ConflictError on commit is caught and the transaction aborted."""
        user = self._user_dict(
            username="erin", keycloak_id="uid-4", municipalities=["mons"]
        )
        with api.env.adopt_roles(["Manager"]):
            self._make_user("erin", "erin", "erin@example.com")
            api.content.create(container=portal, type="Folder", id="mons", title="Mons")
            with patch(
                "pas.plugins.kimug.utils.get_sso_apps_users_with_municipalities",
                return_value=[user],
            ):
                with patch("pas.plugins.kimug.utils.transaction") as mock_txn:
                    mock_txn.commit.side_effect = ConflictError()
                    utils.set_sso_apps_local_roles(portal)
                    mock_txn.abort.assert_called_once()


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

    def test_missing_log_record_does_not_crash(self, portal):
        """If the pas.plugins.kimug.log record is not registered (not-yet-upgraded
        site), set_oidc_settings must not crash and must leave the record absent."""
        registry = getUtility(IRegistry)
        del registry.records["pas.plugins.kimug.log"]

        env = {k: v for k, v in os.environ.items() if k != "KIMUG_LOG"}
        with patch.dict(os.environ, env, clear=True):
            with patch("pas.plugins.kimug.utils.transaction"):
                utils.set_oidc_settings(None)

        assert (
            api.portal.get_registry_record("pas.plugins.kimug.log", default=None)
            is None
        )

    def test_log_record_set_to_false_when_present(self, portal):
        """When the record exists and KIMUG_LOG is not 'true', it is set to False."""
        api.portal.set_registry_record("pas.plugins.kimug.log", True)

        env = {k: v for k, v in os.environ.items() if k != "KIMUG_LOG"}
        with patch.dict(os.environ, env, clear=True):
            with patch("pas.plugins.kimug.utils.transaction"):
                utils.set_oidc_settings(None)

        assert is_log_active() is False
        api.portal.set_registry_record("pas.plugins.kimug.log", False)

    def test_log_record_unchanged_when_kimug_log_true(self, portal):
        """When KIMUG_LOG is 'true', the record is left untouched."""
        api.portal.set_registry_record("pas.plugins.kimug.log", True)

        with patch.dict(os.environ, {"KIMUG_LOG": "true"}):
            with patch("pas.plugins.kimug.utils.transaction"):
                utils.set_oidc_settings(None)

        assert is_log_active() is True
        api.portal.set_registry_record("pas.plugins.kimug.log", False)


class TestIsLogActive:
    def test_is_log_active_default_false(self, portal):
        """is_log_active returns False when registry record is set to False (default)."""
        assert is_log_active() is False

    def test_is_log_active_true(self, portal):
        """is_log_active returns True when registry record is set to True."""
        api.portal.set_registry_record("pas.plugins.kimug.log", True)
        assert is_log_active() is True
        api.portal.set_registry_record("pas.plugins.kimug.log", False)
