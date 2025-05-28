from plone import api

import ast
import logging
import os
import re
import requests
import transaction


logger = logging.getLogger("collective.big.bang.utils")


def sanitize_redirect_uris(redirect_uris: tuple | list | str) -> tuple[str, ...]:
    """Sanitize redirect_uris to ensure they are in the correct format."""
    if isinstance(redirect_uris, tuple):
        # redirect_uris = ('http://url1', 'http://url2', 'http://url3')
        return redirect_uris
    elif isinstance(redirect_uris, list):
        # redirect_uris = ['http://url1', 'http://url2', 'http://url3']
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
                return ()


def get_redirect_uris(current_redirect_uris: tuple[str, ...]) -> tuple[str, ...]:
    """Get redirect_uris from environment variables."""
    website_hostname = os.environ.get("website_hostname")
    if website_hostname is not None:
        website_hostname = f"https://{website_hostname}"
    else:
        website_hostname = "http://localhost:8080/Plone"
    default_redirect_uri = f"{website_hostname}/acl_users/oidc/callback"
    redirect_uris = os.environ.get(
        "keycloak_redirect_uris",
        f"({default_redirect_uri},)",
    )
    redirect_uris = sanitize_redirect_uris(redirect_uris)
    redirect_uris = current_redirect_uris + redirect_uris
    if default_redirect_uri not in redirect_uris:
        # the default redirect uri should always be present
        redirect_uris = redirect_uris + (default_redirect_uri,)
    redirect_uris = list(redirect_uris)

    # handle the case when we went to prod from preprod
    # and the preprod uri is still in the redirect_uris
    preprod_uri = "preprod.imio.be"
    if preprod_uri not in default_redirect_uri:
        for uri in redirect_uris:
            if preprod_uri in uri:
                redirect_uris.remove(uri)
    # remove duplicates
    redirect_uris = list(dict.fromkeys(redirect_uris))
    return tuple(redirect_uris)


def set_oidc_settings(context):
    oidc = get_plugin()
    realm = os.environ.get("keycloak_realm", "plone")
    client_id = os.environ.get("keycloak_client_id", "plone")
    client_secret = os.environ.get("keycloak_client_secret", "12345678910")
    issuer = os.environ.get(
        "keycloak_issuer", f"http://keycloak.traefik.me/realms/{realm}/"
    )
    oidc.redirect_uris = get_redirect_uris(oidc.redirect_uris)
    oidc.client_id = client_id
    oidc.client_secret = client_secret
    oidc.create_groups = True
    oidc.issuer = issuer
    oidc.scope = ("openid", "profile", "email")

    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")

    transaction.commit()
    # return site


def get_admin_access_token(keycloak_url, username, password):
    url = f"{keycloak_url}realms/master/protocol/openid-connect/token"
    payload = {
        "client_id": "admin-cli",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url=url, headers=headers, data=payload)
    access_token = response.json()["access_token"]
    return access_token


def get_plugin():
    """Get the OIDC plugin."""
    pas = api.portal.get_tool("acl_users")
    oidc = pas.oidc
    return oidc


def get_keycloak_users():
    """Get all keycloak users."""
    # realm = os.environ.get("keycloak_realm", None)
    realms = os.environ.get("keycloak_realms", None)
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    # acl_users = api.portal.get_tool("acl_users")
    # oidc = acl_users.oidc
    # realm = oidc.issuer.split("/")[-1]
    kc_users = []
    for realm in [r.strip() for r in realms.split(",")]:
        url = f"{keycloak_url}admin/realms/{realm}/users"
        headers = {"Authorization": "Bearer " + access_token}
        response = requests.get(url=url, headers=headers)
        if response.status_code == 200 and response.json():
            kc_users.extend(response.json())
    return kc_users


def migrate_plone_user_id_to_keycloak_user_id(plone_users, keycloak_users):
    """Migrate keycloak user id to plone user id."""
    for plone_user in plone_users:
        for keycloak_user in keycloak_users:
            if plone_user.getProperty("email") == keycloak_user["email"]:
                # plone_user.id = keycloak_user["id"]
                # save user to pas_plugins.oidc
                oidc = get_plugin()
                new_user = oidc._create_user(keycloak_user["id"])
                userinfo = {
                    "name": plone_user.getUserName(),
                    "email": keycloak_user["email"],
                    "given_name": keycloak_user["firstName"],
                    "family_name": keycloak_user["lastName"],
                }
                oidc._update_user(new_user, userinfo, first_login=True)

                # update owner
                update_owner(plone_user.id, keycloak_user["id"])

                # remove user from source_users or from pas_plugins.authentic
                # __import__("ipdb").set_trace()
                api.user.delete(username=plone_user.id)
                # plone_user.reindexObject()
                logger.info(
                    f"User {plone_user.id} migrated to Keycloak user {keycloak_user['id']}"
                )


def update_owner(plone_user_id, keycloak_user_id):
    """Update the owner of the object."""
    # get all objects owned by plone_user_id
    catalog = api.portal.get_tool("portal_catalog")
    brains = catalog(
        {
            "Creator": plone_user_id,
        }
    )
    for brain in brains:
        obj = brain.getObject()
        old_modification_date = obj.ModificationDate()
        _change_ownership(obj, plone_user_id, keycloak_user_id)
        obj.reindexObject()
        obj.setModificationDate(old_modification_date)
        obj.reindexObject(idxs=["modified"])


def _change_ownership(obj, old_creator, new_owner):
    """Change object ownership"""

    # 1. Change object ownership
    acl_users = api.portal.get_tool("acl_users")
    membership = api.portal.get_tool("portal_membership")
    user = acl_users.getUserById(new_owner)

    if user is None:
        user = membership.getMemberById(new_owner)
        if user is None:
            raise KeyError("Only retrievable users in this site can be made owners.")

    obj.changeOwnership(user)

    creators = list(obj.listCreators())
    if old_creator in creators:
        creators.remove(old_creator)
    if new_owner in creators:
        # Don't add same creator twice, but move to front
        del creators[creators.index(new_owner)]
    obj.setCreators([new_owner] + creators)
