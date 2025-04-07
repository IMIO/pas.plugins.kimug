from plone import api

import ast
import os
import re
import transaction


def sanitize_redirect_uris(redirect_uris):
    """Sanitize redirect_uris to ensure they are in the correct format."""
    if isinstance(redirect_uris, tuple):
        # redirect_uris = "('http://url1', 'http://url2', 'http://url3')"
        return redirect_uris
    else:
        if isinstance(redirect_uris, list):
            # redirect_uris = "['http://url1', 'http://url2', 'http://url3']"
            return tuple(redirect_uris)
        elif isinstance(redirect_uris, str):
            pattern = r"\[((?:[^'\"[\],]+(?:, )?)+)\]"
            if re.match(pattern, redirect_uris):
                # redirect_uris = "[http://url1, http://url2, http://url3]"
                redirect_uris = redirect_uris.strip("[]")
                redirect_uris = redirect_uris.split(", ")
                return tuple(redirect_uris)
            else:
                try:
                    # redirect_uris = "['http://url1', 'http://url2', 'http://url3']"
                    return tuple(ast.literal_eval(redirect_uris))
                except (ValueError, SyntaxError):
                    # redirect_uris is malformed
                    return None


def set_oidc_settings(context):
    site = api.portal.get()
    acl_user = site.acl_users
    oidc = acl_user.oidc
    client_id = os.environ.get("keycloak_client_id", "plone")
    client_secret = os.environ.get("keycloak_client_secret", "12345678910")
    issuer = os.environ.get(
        "keycloak_issuer", "http://keycloak.traefik.me/realms/plone/"
    )
    redirect_uris = os.environ.get(
        "keycloak_redirect_uris",
        "('http://localhost:8080/Plone/acl_users/oidc/callback',)",
    )
    oidc.redirect_uris = sanitize_redirect_uris(redirect_uris)
    oidc.client_id = client_id
    oidc.client_secret = client_secret
    oidc.create_groups = True
    oidc.issuer = issuer
    oidc.scope = ("openid", "profile", "email")

    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")

    transaction.commit()
    return site
