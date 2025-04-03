from pas.plugins.kimug.plugin import KimugPlugin
from plone import api
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

import os


@implementer(INonInstallable)
class HiddenProfiles:
    def getNonInstallableProfiles(self):
        """Hide uninstall profile from site-creation and quickinstaller."""
        return [
            "pas.plugins.kimug:default",
            "pas.plugins.kimug:uninstall",
            "pas.plugins.oidc:default",
        ]


def _add_plugin(pas, pluginid="oidc"):
    if pluginid in pas.objectIds():
        return pluginid + " already installed."
    plugin = KimugPlugin(pluginid, title="OIDC")
    pas._setObject(pluginid, plugin)
    plugin = pas[plugin.getId()]  # get plugin acquisition wrapped!
    for info in pas.plugins.listPluginTypeInfo():
        interface = info["interface"]
        if not interface.providedBy(plugin):
            continue
        pas.plugins.activatePlugin(interface, plugin.getId())
        pas.plugins.movePluginsDown(
            interface, [x[0] for x in pas.plugins.listPlugins(interface)[:-1]]
        )


def post_install(context):
    """Post install script"""
    _add_plugin(api.portal.get_tool("acl_users"))

    site = api.portal.get()
    acl_user = site.acl_users
    oidc = acl_user.oidc
    client_id = os.environ.get("keycloak_client_id", "plone")
    client_secret = os.environ.get("keycloak_client_secret", "12345678910")
    issuer = os.environ.get(
        "keycloak_issuer", "http://keycloak.traefik.me/realms/plone/"
    )
    redirect_uris = os.environ.get(
        "keycloak_redirect_uris", "http://localhost:8080/Plone/acl_users/oidc/callback"
    )
    oidc.client_id = client_id
    oidc.client_secret = client_secret
    oidc.create_groups = True
    oidc.issuer = issuer
    oidc.redirect_uris = (redirect_uris,)
    oidc.scope = ("openid", "profile", "email")

    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")

    # transaction.commit()
    # return site
