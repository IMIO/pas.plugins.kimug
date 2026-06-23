from plone import api


class TestGrantKimugAuthenticatedRole:
    def test_grants_role_to_kimug_users(self, portal):
        """Existing users with an @kimug.be email get the role."""
        from pas.plugins.kimug.plugin import KIMUG_AUTHENTICATED_ROLE
        from pas.plugins.kimug.upgrades import grant_kimug_authenticated_role

        with api.env.adopt_roles(["Manager"]):
            api.user.create(username="plugin-user", email="plugin-user@kimug.be")
            grant_kimug_authenticated_role(None)
            user = api.user.get(userid="plugin-user")
        assert KIMUG_AUTHENTICATED_ROLE in user.getRoles()

    def test_skips_non_kimug_users(self, portal):
        """Users whose email is not @kimug.be are left untouched."""
        from pas.plugins.kimug.plugin import KIMUG_AUTHENTICATED_ROLE
        from pas.plugins.kimug.upgrades import grant_kimug_authenticated_role

        with api.env.adopt_roles(["Manager"]):
            api.user.create(username="local-user", email="local@example.com")
            grant_kimug_authenticated_role(None)
            user = api.user.get(userid="local-user")
        assert KIMUG_AUTHENTICATED_ROLE not in user.getRoles()
