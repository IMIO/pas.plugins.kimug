from plone import api
from plone.distribution.core import Distribution
from Products.CMFPlone.Portal import PloneSite

import os
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

    transaction.commit()
    return site
