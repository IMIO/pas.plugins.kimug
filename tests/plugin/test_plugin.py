from oic.oic.message import OpenIDSchema
from plone import api
from unittest.mock import MagicMock
from unittest.mock import patch

import jwt
import os
import pytest
import requests


class TestPlugin:
    @pytest.fixture(autouse=True)
    def _isolate_jwks_class_state(self):
        """Snapshot and restore KimugPlugin's mutable class-level JWKS caches so
        tests that mutate them do not leak state into later tests."""
        from pas.plugins.kimug.plugin import KimugPlugin

        saved = {
            attr: dict(getattr(KimugPlugin, attr))
            for attr in (
                "_jwks_clients",
                "_jwks_clients_created_at",
                "_jwks_failed_at",
            )
        }
        yield
        for attr, original in saved.items():
            live = getattr(KimugPlugin, attr)
            live.clear()
            live.update(original)

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
        """_ensure_user_exists should create a Plone user with email from payload."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            plugin._ensure_user_exists(
                "new-uid",
                {"email": "new@example.com", "preferred_username": "new-user"},
            )
            user = api.user.get(userid="new-uid")
        assert user is not None
        assert user.getProperty("email") == "new@example.com"

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

    def test_ensure_user_exists_swallows_exceptions(self, portal):
        """_ensure_user_exists must not propagate exceptions from _create_user."""
        plugin = portal.acl_users.oidc
        with patch(
            "pas.plugins.kimug.plugin.KimugPlugin._create_user",
            side_effect=ValueError("boom"),
        ):
            plugin._ensure_user_exists(
                "boom-user", {"email": "x@x.com", "preferred_username": "x"}
            )

    def test_ensure_user_exists_fills_email_from_username(self, portal):
        """_ensure_user_exists should default email to {username}@kimug.be when email is absent."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            plugin._ensure_user_exists(
                "uid-no-email", {"preferred_username": "ssouser"}
            )
            user = api.user.get(userid="uid-no-email")
        assert user is not None
        assert user.getProperty("email") == "ssouser@kimug.be"

    def test_ensure_user_exists_fills_names_from_username(self, portal):
        """_ensure_user_exists should set given_name=username, family_name='sso-apps' when both are absent."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            with patch.object(plugin, "_update_user") as mock_update:
                plugin._ensure_user_exists(
                    "uid-no-names", {"preferred_username": "ssouser"}
                )
                userinfo_arg = mock_update.call_args[0][1]
        assert userinfo_arg["given_name"] == "ssouser"
        assert userinfo_arg["family_name"] == "sso-apps"

    def test_ensure_user_exists_no_default_when_username_empty(self, portal):
        """_ensure_user_exists must not apply any defaults when username is empty."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            with patch.object(plugin, "_update_user") as mock_update:
                plugin._ensure_user_exists(
                    "uid-empty-username", {"preferred_username": ""}
                )
                userinfo_arg = mock_update.call_args[0][1]
        assert userinfo_arg["email"] == ""
        assert userinfo_arg["given_name"] == ""
        assert userinfo_arg["family_name"] == ""

    def test_ensure_user_exists_partial_name_not_overridden(self, portal):
        """_ensure_user_exists must not touch names when at least one of given_name/family_name is set."""
        plugin = portal.acl_users.oidc
        with api.env.adopt_roles(["Manager"]):
            with patch.object(plugin, "_update_user") as mock_update:
                plugin._ensure_user_exists(
                    "uid-partial-name",
                    {
                        "preferred_username": "ssouser",
                        "given_name": "Alice",
                        "family_name": "",
                    },
                )
                userinfo_arg = mock_update.call_args[0][1]
        assert userinfo_arg["given_name"] == "Alice"
        assert userinfo_arg["family_name"] == ""

    def test_ensure_user_exists_populates_from_sso_apps_token(self, portal):
        """A real sso-apps ID token (preferred_username only, no email/name) should
        still yield a user with the {username}@kimug.be email and a fullname."""
        plugin = portal.acl_users.oidc
        payload = {
            "sub": "4661c32b-bf16-4f85-bac9-09014820c399",
            "typ": "ID",
            "email_verified": False,
            "preferred_username": "imio-apps-teleservices_imio-ic-staging2",
        }
        with api.env.adopt_roles(["Manager"]):
            plugin._ensure_user_exists(payload["sub"], payload)
            user = api.user.get(userid=payload["sub"])
        assert user is not None
        assert (
            user.getProperty("email")
            == "imio-apps-teleservices_imio-ic-staging2@kimug.be"
        )
        assert (
            user.getProperty("fullname")
            == "imio-apps-teleservices_imio-ic-staging2 sso-apps"
        )

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
            timeout=30,
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

    def test_authenticate_routes_sso_apps_issuer(self, portal, monkeypatch):
        """authenticateCredentials should call _decode_token(plugin='oidc_sso_apps') for sso-apps tokens."""
        monkeypatch.delenv("SSO_APPS_ACCESS_GROUP", raising=False)
        token = jwt.encode(
            {
                "iss": "https://keycloak.example.com/realms/sso-apps",
                "sub": "sso-sub",
                "groups": ["access_imio-apps-kimug"],
            },
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        with patch(
            "pas.plugins.kimug.plugin.KimugPlugin._decode_token",
            return_value={
                "sub": "sso-sub",
                "email": "sso@example.com",
                "preferred_username": "sso-user",
            },
        ) as mock_decode:
            plugin.authenticateCredentials({"token": token})
            mock_decode.assert_called_once_with(token, plugin="oidc_sso_apps")

    def test_sso_apps_rejects_token_with_no_groups(self, portal):
        """authenticateCredentials must return None when the sso-apps token carries no groups claim."""
        token = jwt.encode(
            {"iss": "https://keycloak.example.com/realms/sso-apps", "sub": "sso-sub"},
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        with patch("pas.plugins.kimug.plugin.KimugPlugin._decode_token") as mock_decode:
            result = plugin.authenticateCredentials({"token": token})
        assert result is None
        mock_decode.assert_not_called()

    def test_sso_apps_rejects_token_missing_access_group(self, portal):
        """authenticateCredentials must return None when the user is not in the required access group."""
        token = jwt.encode(
            {
                "iss": "https://keycloak.example.com/realms/sso-apps",
                "sub": "sso-sub",
                "groups": ["some-other-group"],
            },
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        with patch("pas.plugins.kimug.plugin.KimugPlugin._decode_token") as mock_decode:
            result = plugin.authenticateCredentials({"token": token})
        assert result is None
        mock_decode.assert_not_called()

    def test_sso_apps_accepts_token_with_default_access_group(
        self, portal, monkeypatch
    ):
        """authenticateCredentials must proceed when the token contains the default access group."""
        monkeypatch.delenv("SSO_APPS_ACCESS_GROUP", raising=False)
        token = jwt.encode(
            {
                "iss": "https://keycloak.example.com/realms/sso-apps",
                "sub": "sso-sub",
                "groups": ["access_imio-apps-kimug"],
            },
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        with patch(
            "pas.plugins.kimug.plugin.KimugPlugin._decode_token",
            return_value={
                "sub": "sso-sub",
                "email": "sso@example.com",
                "preferred_username": "sso-user",
            },
        ) as mock_decode:
            plugin.authenticateCredentials({"token": token})
        mock_decode.assert_called_once_with(token, plugin="oidc_sso_apps")

    def test_sso_apps_accepts_token_with_custom_access_group(self, portal):
        """authenticateCredentials must honour SSO_APPS_ACCESS_GROUP when set."""
        token = jwt.encode(
            {
                "iss": "https://keycloak.example.com/realms/sso-apps",
                "sub": "sso-sub",
                "groups": ["my-custom-group"],
            },
            "secret",
            algorithm="HS256",
        )
        plugin = portal.acl_users.oidc
        os.environ["SSO_APPS_ACCESS_GROUP"] = "my-custom-group"
        try:
            with patch(
                "pas.plugins.kimug.plugin.KimugPlugin._decode_token",
                return_value={
                    "sub": "sso-sub",
                    "email": "sso@example.com",
                    "preferred_username": "sso-user",
                },
            ) as mock_decode:
                plugin.authenticateCredentials({"token": token})
            mock_decode.assert_called_once_with(token, plugin="oidc_sso_apps")
        finally:
            del os.environ["SSO_APPS_ACCESS_GROUP"]

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

    def test_decode_token_sso_apps_audience_default(self, portal, monkeypatch):
        """_decode_token uses 'imio-apps-plone' when neither SSO_APPS_AUDIENCE nor SSO_APPS_CLIENT_ID is set."""
        monkeypatch.delenv("SSO_APPS_AUDIENCE", raising=False)
        monkeypatch.delenv("SSO_APPS_CLIENT_ID", raising=False)
        plugin = portal.acl_users.oidc
        mock_key = MagicMock()
        mock_key.key = "key"
        with patch.object(plugin, "_get_jwks_client") as mock_client, patch(
            "pas.plugins.kimug.plugin.jwt.decode", return_value={"sub": "x"}
        ) as mock_decode:
            mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
            plugin._decode_token("fake.token", plugin="oidc_sso_apps")
        assert mock_decode.call_args.kwargs["audience"] == "imio-apps-plone"

    def test_decode_token_sso_apps_audience_from_client_id(self, portal, monkeypatch):
        """_decode_token falls back to SSO_APPS_CLIENT_ID when SSO_APPS_AUDIENCE is not set."""
        monkeypatch.delenv("SSO_APPS_AUDIENCE", raising=False)
        monkeypatch.setenv("SSO_APPS_CLIENT_ID", "my-client")
        plugin = portal.acl_users.oidc
        mock_key = MagicMock()
        mock_key.key = "key"
        with patch.object(plugin, "_get_jwks_client") as mock_client, patch(
            "pas.plugins.kimug.plugin.jwt.decode", return_value={"sub": "x"}
        ) as mock_decode:
            mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
            plugin._decode_token("fake.token", plugin="oidc_sso_apps")
        assert mock_decode.call_args.kwargs["audience"] == "my-client"

    def test_decode_token_sso_apps_audience_env_takes_priority(
        self, portal, monkeypatch
    ):
        """SSO_APPS_AUDIENCE takes priority over SSO_APPS_CLIENT_ID."""
        monkeypatch.setenv("SSO_APPS_AUDIENCE", "explicit-audience")
        monkeypatch.setenv("SSO_APPS_CLIENT_ID", "client-id")
        plugin = portal.acl_users.oidc
        mock_key = MagicMock()
        mock_key.key = "key"
        with patch.object(plugin, "_get_jwks_client") as mock_client, patch(
            "pas.plugins.kimug.plugin.jwt.decode", return_value={"sub": "x"}
        ) as mock_decode:
            mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
            plugin._decode_token("fake.token", plugin="oidc_sso_apps")
        assert mock_decode.call_args.kwargs["audience"] == "explicit-audience"

    def test_get_jwks_client_cached_per_realm(self, portal, monkeypatch):
        """Each realm must get its own JWKS client. A single shared client would
        be handed to the wrong realm, whose tokens never match the cached keyset
        and force a JWKS refetch on every request (the cause of the sticky 403).
        """
        from pas.plugins.kimug.plugin import KimugPlugin

        # PyJWKClient does no network I/O at construction, so this is offline.
        monkeypatch.setenv("keycloak_url", "https://kc-oidc.example.com/")
        monkeypatch.setenv("keycloak_realm", "plone")
        monkeypatch.setenv("SSO_APPS_URL", "https://kc-sso.example.com/")
        monkeypatch.setenv("SSO_APPS_REALM", "sso-apps")
        # Start from a clean class-level cache for a deterministic assertion.
        KimugPlugin._jwks_clients.clear()
        KimugPlugin._jwks_clients_created_at.clear()

        plugin = portal.acl_users.oidc
        oidc_client = plugin._get_jwks_client(plugin="oidc")
        sso_client = plugin._get_jwks_client(plugin="oidc_sso_apps")

        assert oidc_client is not sso_client
        assert oidc_client.uri == (
            "https://kc-oidc.example.com/realms/plone/protocol/openid-connect/certs"
        )
        assert sso_client.uri == (
            "https://kc-sso.example.com/realms/sso-apps/protocol/openid-connect/certs"
        )
        # Same realm returns the cached instance rather than rebuilding.
        assert plugin._get_jwks_client(plugin="oidc") is oidc_client
        assert plugin._get_jwks_client(plugin="oidc_sso_apps") is sso_client

    def test_decode_token_failure_triggers_cooldown(self, portal):
        """After a JWKS failure, an immediate retry must short-circuit without
        hitting the endpoint again — this is the backoff that prevents a
        transient 403 from becoming a self-sustaining fetch storm.
        """
        from jwt.exceptions import PyJWKClientError
        from pas.plugins.kimug.plugin import KimugPlugin

        KimugPlugin._jwks_failed_at.clear()
        plugin = portal.acl_users.oidc
        mock_client = MagicMock()
        mock_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("boom")
        with patch.object(plugin, "_get_jwks_client", return_value=mock_client):
            first = plugin._decode_token("fake.token", plugin="oidc")
            second = plugin._decode_token("fake.token", plugin="oidc")
        assert first is None
        assert second is None
        # Second call was suppressed by the cooldown, so only one fetch attempt.
        assert mock_client.get_signing_key_from_jwt.call_count == 1
        assert "oidc" in KimugPlugin._jwks_failed_at

    def test_decode_token_retries_after_cooldown_elapsed(self, portal):
        """Once the cooldown window has passed, the next call must attempt the
        JWKS fetch again rather than staying suppressed forever.
        """
        from jwt.exceptions import PyJWKClientError
        from pas.plugins.kimug.plugin import KimugPlugin

        # Mark a failure far enough in the past that the cooldown has elapsed.
        KimugPlugin._jwks_failed_at["oidc"] = 0.0
        plugin = portal.acl_users.oidc
        mock_client = MagicMock()
        mock_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("boom")
        with patch.object(plugin, "_get_jwks_client", return_value=mock_client):
            result = plugin._decode_token("fake.token", plugin="oidc")
        assert result is None
        assert mock_client.get_signing_key_from_jwt.call_count == 1

    def test_decode_token_success_clears_cooldown(self, portal, monkeypatch):
        """A successful key fetch must clear any prior failure marker so the
        realm is not left in a stale backoff state.
        """
        from pas.plugins.kimug.plugin import KimugPlugin

        KimugPlugin._jwks_failed_at["oidc"] = 0.0
        plugin = portal.acl_users.oidc
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client = MagicMock()
        mock_client.get_signing_key_from_jwt.return_value = mock_key
        with patch.object(plugin, "_get_jwks_client", return_value=mock_client), patch(
            "pas.plugins.kimug.plugin.jwt.decode", return_value={"sub": "x"}
        ):
            plugin._decode_token("fake.token", plugin="oidc")
        assert "oidc" not in KimugPlugin._jwks_failed_at
