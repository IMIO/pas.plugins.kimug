from oic.oic.message import OpenIDSchema
from plone import api
from unittest.mock import patch

import jwt
import os
import requests


class TestPlugin:
    def _initialize(self, portal):
        pas = api.portal.get_tool("acl_users")
        plugin = getattr(pas, "oidc")
        self.portal_url = api.portal.get().absolute_url()
        self.plugin_url = plugin.absolute_url()

    def test_login_with_bearer(self, portal, keycloak_service, keycloak_issuer):
        """Test login with bearer token."""

        payload = {
            "grant_type": "password",
            "client_id": "keycloak-idp",
            "client_secret": "12345678910",
            "username": "kimug",
            "password": "kimug",
            "scope": ["openid"],
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = requests.post(
            f"{keycloak_service}/realms/imio/protocol/openid-connect/token",
            headers=headers,
            data=payload,
        ).json()
        access_token = response.get("access_token")
        access_token_decoded = jwt.decode(
            access_token, options={"verify_signature": False}
        )
        assert access_token_decoded.get("groups") == ["smartweb"]

        pas = api.portal.get_tool("acl_users")
        plugin = getattr(pas, "oidc")
        result = plugin.authenticateCredentials({"token": access_token})
        assert result is not None, "Bearer JWT must verify against Keycloak JWKS"
        user_id, _login = result
        assert user_id == access_token_decoded["sub"]

    def test_create_user(self, browser_layers):
        """Test that IBrowserLayer is registered."""
        pas = api.portal.get_tool("acl_users")
        plugin = getattr(pas, "oidc")
        userinfo = OpenIDSchema(sub="kimug", groups=["smartweb"])
        assert pas.getUserById("kimug") is None
        # Remember identity
        plugin.rememberIdentity(userinfo)
        assert pas.getUserById("kimug") is not None
        assert api.user.get_users()[0].getUserId() == "kimug"

    def test_ensure_user_exists_creates_user(self, portal):
        """_ensure_user_exists should create a Plone user with email and fullname from payload."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            plugin._ensure_user_exists(
                "new-uid", {"email": "new@example.com", "name": "New User"}
            )
            user = api.user.get(userid="new-uid")
        assert user is not None
        assert user.getProperty("email") == "new@example.com"
        assert user.getProperty("fullname") == "New User"

    def test_ensure_user_exists_skips_existing_user(self, portal):
        """_ensure_user_exists should not modify an existing user."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            api.user.create(username="existing-user", email="orig@example.com")
            plugin._ensure_user_exists(
                "existing-user", {"email": "changed@example.com"}
            )
            user = api.user.get(userid="existing-user")
        assert user.getProperty("email") == "orig@example.com"

    def test_ensure_user_exists_uses_fallback_email(self, portal):
        """_ensure_user_exists should use {userid}@keycloak.local when email is absent."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            plugin._ensure_user_exists("no-email-user", {})
            user = api.user.get(userid="no-email-user")
        assert user is not None
        assert user.getProperty("email") == "no-email-user@keycloak.local"

    def test_ensure_user_exists_swallows_exceptions(self, portal):
        """_ensure_user_exists must not propagate exceptions from api.user.create."""
        plugin = portal.acl_users.oidc
        with patch(
            "pas.plugins.kimug.plugin.api.user.create", side_effect=ValueError("boom")
        ):
            plugin._ensure_user_exists("boom-user", {"email": "x@x.com"})

    def test_authenticate_creates_user_on_first_login(
        self, portal, keycloak_service, keycloak_issuer
    ):
        """authenticateCredentials should auto-create the Plone user on first successful JWT auth."""
        payload = {
            "grant_type": "password",
            "client_id": "keycloak-idp",
            "client_secret": "12345678910",
            "username": "kimug",
            "password": "kimug",
            "scope": ["openid"],
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            f"{keycloak_service}/realms/imio/protocol/openid-connect/token",
            headers=headers,
            data=payload,
        ).json()
        access_token = response.get("access_token")
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        user_id = decoded["sub"]

        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            result = plugin.authenticateCredentials({"token": access_token})
            user = api.user.get(userid=user_id)

        assert result is not None
        assert user is not None, "User should be auto-created after first JWT auth"

    def test_authenticate_routes_sso_apps_issuer(self, portal):
        """authenticateCredentials should call _decode_token(plugin='oidc_sso_apps') for sso-apps tokens."""
        token = jwt.encode(
            {"iss": "https://keycloak.example.com/realms/sso-apps", "sub": "sso-sub"},
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        with patch(
            "pas.plugins.kimug.plugin.KimugPlugin._decode_token",
            return_value={"sub": "sso-sub", "email": "sso@example.com"},
        ) as mock_decode:
            plugin.authenticateCredentials({"token": token})
            mock_decode.assert_called_once_with(token, plugin="oidc_sso_apps")

    def test_groups_roles(self, profile_last_version):
        """Test latest version of default profile."""
        pas = api.portal.get_tool("acl_users")
        plugin = getattr(pas, "oidc")
        userinfo = OpenIDSchema(sub="kimug", groups=["delib"])
        userinfo_with_groups = OpenIDSchema(
            sub="kimug_with_groups", groups=["smartweb"]
        )
        plugin.rememberIdentity(userinfo)
        plugin.rememberIdentity(userinfo_with_groups)
        role = plugin.getRolesForPrincipal(pas.getUserById("kimug"))
        roles = plugin.getRolesForPrincipal(pas.getUserById("kimug_with_groups"))
        assert role == ("Member",)
        # assert roles == ("Member", "Manager")
        assert roles == (
            "Member",
        )  # https://github.com/IMIO/pas.plugins.kimug/commit/966d16cabd44379e12cfd580bff80e58a72f98bb
        os.environ["application_id"] = "delib"
        roles = plugin.getRolesForPrincipal(pas.getUserById("kimug"))
        # assert roles == ("Member", "Manager")
        assert roles == (
            "Member",
        )  # https://github.com/IMIO/pas.plugins.kimug/commit/966d16cabd44379e12cfd580bff80e58a72f98bb
        del os.environ["application_id"]
