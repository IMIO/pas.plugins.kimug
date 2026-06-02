from pas.plugins.kimug.setuphandlers import _add_plugin
from pas.plugins.kimug.utils import add_keycloak_users_to_plone
from pas.plugins.kimug.utils import get_keycloak_users_from_oidc_sso_apps
from pas.plugins.kimug.utils import set_oidc_settings
from plone import api


def add_oidc_sso_apps_plugin(context):
    """Upgrade step to add oidc_sso_apps plugin."""
    _add_plugin(
        api.portal.get_tool("acl_users"),
        pluginid="oidc_sso_apps",
        title="OIDC SSO Apps",
    )
    set_oidc_settings(api.portal.get())
    users = get_keycloak_users_from_oidc_sso_apps()
    add_keycloak_users_to_plone(users)
