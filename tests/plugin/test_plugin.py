from oic.oic.message import OpenIDSchema
from plone import api

import jwt
import os
import requests


class TestPlugin:
    def _initialize(self, portal):
        pas = api.portal.get_tool("acl_users")
        plugin = getattr(pas, "oidc")
        self.portal_url = api.portal.get().absolute_url()
        self.plugin_url = plugin.absolute_url()

    def test_login_with_bearer(self, portal):
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
            "http://keycloak.traefik.me/realms/imio/protocol/openid-connect/token",
            headers=headers,
            data=payload,
        ).json()
        access_token = response.get("access_token")
        access_token_decoded = jwt.decode(
            access_token, options={"verify_signature": False}
        )
        assert access_token_decoded.get("groups") == ["smartweb"]

        headers = {"Authorization": f"Bearer {access_token}"}
        response_bearer = requests.get(
            "http://keycloak.traefik.me/realms/imio/protocol/openid-connect/userinfo",
            headers=headers,
        )
        response_bearer.raise_for_status()
        assert response_bearer.status_code == 200

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
        assert roles == ("Member", "Manager")
        os.environ["application_id"] = "delib"
        roles = plugin.getRolesForPrincipal(pas.getUserById("kimug"))
        assert roles == ("Member", "Manager")
        del os.environ["application_id"]
