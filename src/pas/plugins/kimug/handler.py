from plone import api
from plone.distribution.core import Distribution
from Products.CMFPlone.Portal import PloneSite

import transaction


def post_handler(
    distribution: Distribution, site: PloneSite, answers: dict
) -> PloneSite:
    setup_tool = site["portal_setup"]
    # Install profile
    profiles = [
        "pas.plugins.kimug:default",
    ]
    for profile_id in profiles:
        setup_tool.runAllImportStepsFromProfile(f"profile-{profile_id}")

    acl_user = site.acl_users
    oidc = acl_user.oidc
    oidc.client_id = "plone"
    oidc.client_secret = "12345678910"
    oidc.issuer = "http://keycloak.traefik.me/realms/plone/"
    oidc.redirect_uris = ("http://localhost:8080/Plone/acl_users/oidc/callback",)
    oidc.scope = ("openid", "profile", "email")

    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")

    transaction.commit()
    return site
