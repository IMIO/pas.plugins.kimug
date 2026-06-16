from pas.plugins.kimug.setuphandlers import _add_plugin
from pas.plugins.kimug.utils import add_keycloak_users_to_plone
from pas.plugins.kimug.utils import get_keycloak_users_from_oidc_sso_apps
from pas.plugins.kimug.utils import remove_authentic_plugin
from pas.plugins.kimug.utils import set_oidc_settings
from plone import api
from Products.PluggableAuthService.interfaces.plugins import IChallengePlugin

import logging


logger = logging.getLogger(__name__)


def add_oidc_sso_apps_plugin(context):
    """Upgrade step to add oidc_sso_apps plugin."""
    _add_plugin(
        api.portal.get_tool("acl_users"),
        pluginid="oidc_sso_apps",
        title="OIDC SSO Apps",
        challenge=False,
    )
    set_oidc_settings(api.portal.get())
    try:
        users = get_keycloak_users_from_oidc_sso_apps()
        add_keycloak_users_to_plone(users)
    except Exception as e:
        logger.exception(
            "Keycloak user sync failed during upgrade step; "
            "plugin registration is complete. Error: %s",
            e,
        )


def disable_oidc_sso_apps_challenge(context):
    """Remove oidc_sso_apps from IChallengePlugin so oidc handles the login.

    On sites where oidc_sso_apps was already installed, the previous
    registration left it on top of the IChallengePlugin list, hijacking the
    interactive login challenge from the "oidc" plugin.
    """
    pas = api.portal.get_tool("acl_users")
    active = [p[0] for p in pas.plugins.listPlugins(IChallengePlugin)]
    if "oidc_sso_apps" in active:
        pas.plugins.deactivatePlugin(IChallengePlugin, "oidc_sso_apps")


def remove_pas_plugins_imio(context):
    """Remove pas.plugins.imio and authentic plugin from acl_users."""
    remove_authentic_plugin()
