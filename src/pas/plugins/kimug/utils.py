from Acquisition import aq_base
from collections import defaultdict
from plone import api
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
from urllib.parse import urlparse
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import setSite

import ast
import logging
import os
import re
import requests
import time
import transaction


logger = logging.getLogger("pas.plugins.kimug.utils")


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
    website_hostname = os.environ.get("WEBSITE_HOSTNAME")
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


def get_redirect_uri() -> tuple[str, ...]:
    """Get the main redirect_uri from environment variables."""
    website_hostname = os.environ.get("WEBSITE_HOSTNAME")
    if website_hostname is not None:
        redirect_uri = f"https://{website_hostname}"
    else:
        redirect_uri = "http://localhost:8080/Plone"
    redirect_uri = f"{redirect_uri}/acl_users/oidc/callback"
    return (redirect_uri,)


def set_oidc_settings(context):
    """Set the needed OIDC settings so that Keycloak can be used as authentication source."""
    try:
        api.portal.get()
        logger.info("Site found with api.portal.get()")
    except api.exc.CannotGetPortalError:
        logger.info("Site not found with api.portal.get(), setting it with setSite()")
        try:
            site = context.database.open().root()["Application"]["Plone"]
        except KeyError:
            logger.warning("Could not find Plone site, not setting OIDC settings")
            return
        setSite(site)
    if oidc := get_plugin():
        realm = os.environ.get("keycloak_realm", "plone")
        client_id = os.environ.get("keycloak_client_id", "plone")
        client_secret = os.environ.get("keycloak_client_secret", "12345678910")
        issuer = os.environ.get(
            "keycloak_issuer", f"http://keycloak.traefik.me/realms/{realm}/"
        )
        oidc.redirect_uris = get_redirect_uri()
        oidc.client_id = client_id
        oidc.client_secret = client_secret
        oidc.create_groups = True
        oidc.issuer = issuer
        oidc.scope = ("openid", "profile", "email")
        oidc.userinfo_endpoint_method = "GET"

        api.portal.set_registry_record(
            "plone.external_login_url", "acl_users/oidc/login"
        )
        api.portal.set_registry_record(
            "plone.external_logout_url", "acl_users/oidc/logout"
        )

        transaction.commit()
        logger.info("OIDC settings set with set_oidc_settings()")
    else:
        logger.warning("Could not find OIDC plugin, not setting OIDC settings")


def get_admin_access_token(keycloak_url, username, password):
    url = f"{keycloak_url}realms/master/protocol/openid-connect/token"
    payload = {
        "client_id": "admin-cli",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url=url, headers=headers, data=payload).json()
    if response.get("access_token", None) is None:
        logger.error(f"Error getting access token: {response}")
        # raise Exception("Could not get access token from Keycloak" "")
        return None
    access_token = response["access_token"]
    return access_token


def _get_env_default(value, env_var, default=None):
    """Return value if not None, otherwise return env var or default"""
    return value if value is not None else os.getenv(env_var, default)


def get_client_access_token(
    keycloak_url: str = None,
    realm: str = None,
    client_id: str = None,
    client_secret: str = None,
) -> str | None:
    """Get an access token using client_credentials."""
    keycloak_url = _get_env_default(
        keycloak_url, "keycloak_url", "http://keycloak.traefik.me/"
    )
    client_id = _get_env_default(client_id, "keycloak_client_id", "plone")
    client_secret = _get_env_default(
        client_secret, "keycloak_client_secret", "12345678910"
    )
    realm = _get_env_default(realm, "keycloak_realm", "plone")

    url = f"{keycloak_url}realms/{realm}/protocol/openid-connect/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(url=url, headers=headers, data=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(
                f"Error getting access token: HTTP {resp.status_code} - {resp.text}"
            )
            return None
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            logger.error(
                f"Error getting access token: Unexpected content type {content_type}"
            )
            return None
        response = resp.json()
    except Exception as e:
        logger.error(f"Exception getting access token: {e}")
        return None
    if response.get("access_token", None) is None:
        logger.error(f"Error getting access token: {response}")
        return None
    access_token = response["access_token"]
    return access_token


def get_plugin():
    """Get the OIDC plugin."""
    pas = api.portal.get_tool("acl_users")
    try:
        oidc = pas.oidc
    except AttributeError:
        logger.warning("Could not find OIDC plugin with get_plugin().")
        return None
    return oidc


def get_keycloak_users():
    """Get all keycloak users."""
    realm = os.environ.get("keycloak_realm", None)
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    if not access_token:
        logger.error("Could not get access token from Keycloak")
        return []
    kc_users = []
    url = f"{keycloak_url}admin/realms/{realm}/users?max=100000"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url=url, headers=headers)
    if response.status_code == 200 and response.json():
        kc_users.extend(response.json())
    else:
        logger.error(
            f"Error getting users from Keycloak realm {realm}: {response.json()}"
        )
        raise Exception(f"Could not get users from Keycloak realm {realm}")

    kc_users.extend(get_imio_users())
    logger.info(f"Users from Keycloak: {len(kc_users)}")
    return kc_users


def get_imio_users():
    realm = "imio"
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    if not access_token:
        logger.error("Could not get access token from Keycloak")
        return []
    url = f"{keycloak_url}admin/realms/{realm}/users"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url=url, headers=headers)
    if response.status_code == 200 and response.json():
        kc_users = response.json()
    logger.info(f"Users from Keycloak imio realm: {len(kc_users)}")
    return [dict(user, id=None) for user in kc_users]


def create_keycloak_user(email, first_name, last_name):
    """Create a Keycloak user."""
    realm = os.environ.get("keycloak_realm", None)
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    if not access_token:
        logger.error("Could not get access token from Keycloak")
        return None

    url = f"{keycloak_url}admin/realms/{realm}/users"
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
    }
    # Check if the user already exists in the realm
    params = {"email": email}
    check_response = requests.get(
        url, headers={"Authorization": "Bearer " + access_token}, params=params
    )
    if check_response.status_code == 200 and check_response.json():
        logger.info(f"User with email {email} already exists in Keycloak realm {realm}")
        return check_response.json()[0].get("id")

    response = requests.post(url=url, headers=headers, json=payload)
    if response.status_code == 201:
        user_id = response.headers.get("Location").split("/")[-1]
        logger.info(f"User create with email: {email}, id: {user_id}")
        return user_id
    else:
        logger.error(f"Error creating user: {response.json()}")
        return None


def migrate_plone_user_id_to_keycloak_user_id(plone_users, keycloak_users):
    """Migrate keycloak user id to plone user id."""
    disable_authentication_plugins()
    len_plone_users = len(plone_users)
    len_keycloak_users = len(keycloak_users)
    user_migrated = 0
    user_to_delete = []
    old_users = {
        plone_user.getProperty("email"): plone_user.id for plone_user in plone_users
    }

    old_users = defaultdict(list)
    for plone_user in plone_users:
        old_users[plone_user.getProperty("email")].append(plone_user.id)
    list_local_roles = get_list_local_roles()
    try:
        for keycloak_user in keycloak_users:
            plone_users = old_users.get(keycloak_user["email"], [])
            for plone_user in plone_users:
                # __import__("ipdb").set_trace()
                if plone_user is not None and plone_user != keycloak_user["id"]:
                    start = time.time()
                    # plone_user.id = keycloak_user["id"]
                    # save user to pas_plugins.oidc
                    if not keycloak_user["id"]:
                        keycloak_user["id"] = create_keycloak_user(
                            keycloak_user["email"],
                            keycloak_user["firstName"],
                            keycloak_user["lastName"],
                        )
                    if keycloak_user["id"] == plone_user:
                        logger.info(f"User {keycloak_user['email']} already migrated")
                        continue
                    oidc = get_plugin()
                    new_user = oidc._create_user(keycloak_user["id"])

                    # check if new_user exists, it not get user with id
                    if new_user is None:
                        try:
                            new_user = api.user.get(userid=keycloak_user["id"])
                        except Exception as e:
                            logger.debug(f"Error getting user by email: {e}")
                            continue
                    creation = time.time()
                    logging.info(f"time for creation: {creation - start:.4f} secondes")

                    # get roles and groups
                    membership = api.portal.get_tool("portal_membership")
                    member = membership.getMemberById(plone_user)
                    old_roles = member and member.getRoles() or []
                    if "Authenticated" in old_roles:
                        old_roles.remove("Authenticated")
                    if "Anonymous" in old_roles:
                        old_roles.remove("Anonymous")
                    old_groups = (
                        member and api.group.get_groups(username=plone_user) or []
                    )
                    old_group_ids = [group.id for group in old_groups]
                    if "AuthenticatedUsers" in old_group_ids:
                        old_group_ids.remove("AuthenticatedUsers")

                    userinfo = {
                        "username": keycloak_user["email"],
                        "email": keycloak_user["email"],
                        "given_name": keycloak_user["firstName"],
                        "family_name": keycloak_user["lastName"],
                    }
                    try:
                        oidc._update_user(new_user, userinfo, first_login=True)
                    except Exception as e:
                        logger.error(
                            f"Not able to update user {keycloak_user['email']}, {e}"
                        )
                        continue
                    update = time.time()
                    logging.info(
                        f"time for updating user: {update - creation:.4f} secondes"
                    )
                    # update owner
                    logger.info(f"Update owner of {keycloak_user['email']}")
                    update_owner(plone_user, keycloak_user["id"], list_local_roles)
                    owner = time.time()
                    logging.info(f"time for owner user: {owner - update:.4f} secondes")
                    # remove user from source_users or from pas_plugins.authentic
                    # api.user.delete(username=plone_user)
                    user_to_delete.append(plone_user)
                    delete = time.time()
                    logging.info(f"time for delete user: {delete - owner:.4f} secondes")
                    # set old roles to user
                    api.user.grant_roles(username=keycloak_user["id"], roles=old_roles)
                    for group in old_group_ids:
                        api.group.add_user(
                            groupname=group, username=keycloak_user["id"]
                        )
                    logger.info(
                        f"User {plone_user} migrated to Keycloak user {keycloak_user['id']} with email {keycloak_user['email']}"
                    )
                    roles = time.time()
                    logging.info(f"time for roles: {roles - delete:.4f} secondes")
                    # if user_migrated % 10 == 0 and user_migrated != 0:
                    #     start_trans = time.time()
                    transaction.commit()
                    trans = time.time()
                    logging.info(f"time for commit trans: {trans - roles:.4f} secondes")
                    user_migrated += 1
                    logger.info(
                        f"User {user_migrated}/{len_plone_users}  (keycloak: {len_keycloak_users})"
                    )
                    end = time.time()
                    logging.info(f"time for one user: {end - start:.4f} secondes")

        delete_all = time.time()
        portal_membership = api.portal.get_tool("portal_membership")
        portal_membership.deleteMembers(user_to_delete)
        transaction.commit()
        delete_all_end = time.time()
        logging.info(
            f"time delete all users: {delete_all_end - delete_all:.4f} secondes"
        )
    except Exception as e:
        logger.error(f"Error migrating users: {e}")
    finally:
        enable_authentication_plugins()


def update_owner(plone_user_id, keycloak_user_id, list_local_roles):
    """Update the owner of the object."""
    # get all objects owned by plone_user_id
    catalog = api.portal.get_tool("portal_catalog")
    brains = catalog(
        {
            "Creator": plone_user_id,
        }
    )
    logger.info(
        f"Updating ownership for {len(brains)} objects owned by {plone_user_id} to {keycloak_user_id}"
    )
    for brain in brains:
        try:
            obj = brain.getObject()
        except Exception as e:
            logger.error(f"Error getting object for brain {brain}: {e}")
            continue
        old_modification_date = obj.ModificationDate()
        _change_ownership(obj, plone_user_id, keycloak_user_id)
        obj.reindexObject()
        obj.setModificationDate(old_modification_date)
        obj.reindexObject(idxs=["modified"])

    for obj_with_localrole_ in list_local_roles:
        old_modification_date = obj_with_localrole_.ModificationDate()
        _change_local_roles(obj_with_localrole_, plone_user_id, keycloak_user_id)
        obj_with_localrole_.reindexObject()
        obj_with_localrole_.setModificationDate(old_modification_date)
        obj_with_localrole_.reindexObject(idxs=["modified"])


def _change_ownership(obj, old_creator, new_owner):
    """Change object ownership"""

    # Change object ownership
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

    # remove old owners
    roles = list(obj.get_local_roles_for_userid(old_creator))
    if "Owner" in roles:
        roles.remove("Owner")
    if roles:
        obj.manage_setLocalRoles(old_creator, roles)
    else:
        obj.manage_delLocalRoles([old_creator])

    roles = list(obj.get_local_roles_for_userid(new_owner))
    if "Owner" not in roles:
        roles.append("Owner")
        obj.manage_setLocalRoles(new_owner, roles)


def _change_local_roles(obj, old_creator, new_owner):
    # localroles = list(obj.get_local_roles_for_userid(old_creator))
    obj_url = obj.absolute_url()
    if getattr(aq_base(obj), "__ac_local_roles__", None) is not None:
        localroles = obj.__ac_local_roles__
        if old_creator in list(localroles.keys()):
            roles = localroles[old_creator]
            if new_owner != old_creator:
                obj.manage_delLocalRoles([old_creator])
                obj.manage_setLocalRoles(userid=new_owner, roles=roles)
                # obj.reindexObject()
                logger.info(f"Migrated userids in local roles on {obj_url}")


def clean_authentic_users():
    """Clean up the pas_plugins.authentic users."""
    acl_users = api.portal.get_tool("acl_users")
    authentic = acl_users.get("authentic", None)
    user_to_delete = []
    if authentic is None:
        logger.warning("No authentic plugin.")
        return
    for user in authentic.getUsers():
        username = api.user.get(user.getId()).getUserName()
        if "iateleservices" not in username:
            try:
                # admin_user = api.user.get(username="admin")
                update_owner(user.getId(), "admin", [])
                user_to_delete.append(user.getId())
            except KeyError:
                user_to_delete.append(user.getId())
                # user does not exist in Plone, remove from authentic users
                logger.info(
                    f"Removed {user.getProperty('email')} from authentic users."
                )
    portal_membership = api.portal.get_tool("portal_membership")
    portal_membership.deleteMembers(user_to_delete)
    transaction.commit()


def remove_authentic_plugin():
    """Remove the authentic plugin."""

    portal_setup = api.portal.get_tool("portal_setup")
    portal_setup.runAllImportStepsFromProfile("profile-pas.plugins.imio:uninstall")

    acl_users = api.portal.get_tool("acl_users")
    if "authentic" in acl_users.objectIds():
        acl_users.manage_delObjects(["authentic"])
        logger.info("Removed authentic plugin from acl_users.")
    else:
        logger.warning("No authentic plugin to remove.")

    # reset login and logout URLs because they are set by the authentic uninstall
    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")


def disable_authentication_plugins() -> list[str]:
    """Disable all authentication plugins that are enabled."""
    acl_users = api.portal.get_tool("acl_users")
    site = api.portal.get()
    annotations = IAnnotations(site)
    plugins = acl_users.plugins.getAllPlugins(plugin_type="IAuthenticationPlugin")
    disabled_plugins = []
    for plugin in plugins.get("active", ()):
        acl_users.plugins.deactivatePlugin(IAuthenticationPlugin, plugin)
        disabled_plugins.append(plugin)
        logger.info(f"Disabled authentication plugin: {plugin}")
    annotations.setdefault("pas.plugins.kimug.disabled_plugins", []).extend(
        disabled_plugins
    )
    return disabled_plugins


def enable_authentication_plugins() -> None:
    """Enable authentication plugins that were previously disabled with disable_authentication_plugins."""
    site = api.portal.get()
    annotations = IAnnotations(site)
    disabled_plugins = annotations.get("pas.plugins.kimug.disabled_plugins", ()).copy()
    acl_users = api.portal.get_tool("acl_users")
    for plugin in disabled_plugins:
        acl_users.plugins.activatePlugin(IAuthenticationPlugin, plugin)
        annotations["pas.plugins.kimug.disabled_plugins"].remove(plugin)
        logger.info(f"Enabled authentication plugin: {plugin}")


def realm_exists(realm: str) -> bool:
    """Check if a Keycloak realm exists."""
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    if not access_token:
        logger.error("Could not get access token from Keycloak")
        return False

    url = f"{keycloak_url}admin/realms/{realm}"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url=url, headers=headers, timeout=10)
    return response.status_code == 200


def _check_redirect_uris(client_id: str, access_token: str) -> bool:
    """Check if the redirect_uris set in Keycloak match the ones set in the OIDC plugin."""
    oidc = get_plugin()
    keycloak_url = _get_env_default(None, "keycloak_url", "http://keycloak.traefik.me/")
    realm = _get_env_default(None, "keycloak_realm", "plone")
    url = f"{keycloak_url}admin/realms/{realm}/clients?clientId={client_id}"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url=url, headers=headers, timeout=10)
    if response.status_code != 200 or not response.json():
        logger.error(
            f"Error getting client from Keycloak: HTTP {response.status_code} - {response.text}"
        )
        return False
    client = response.json()[0]
    redirect_uris = client.get("redirectUris", [])
    if not redirect_uris:
        logger.error("No redirect_uris found for client")
        return False
    for redirect_uri in redirect_uris:
        if redirect_uri.endswith("/*"):
            redirect_uri = redirect_uri[:-2]
        for oidc_redirect_uri in oidc.redirect_uris:
            if oidc_redirect_uri.startswith(redirect_uri):
                logger.info("Redirect URI in OIDC settings found in Keycloak")
                return True
    return False


def check_keycloak_settings() -> bool:
    """Check if we can get an access token with the OIDC settings.
    And if the redirect_uris set in Keycloak match the ones set in the OIDC plugin.
    """

    oidc = get_plugin()
    if not oidc:
        logger.error("OIDC plugin not found")
        return False
    issuer = oidc.issuer
    if not issuer:
        logger.error("OIDC issuer not set")
        return False
    realm = [item for item in issuer.split("/") if item][-1]
    issuer_parsed = urlparse(issuer)
    if not issuer_parsed.scheme or not issuer_parsed.netloc:
        logger.error("OIDC issuer is not a valid URL")
        return False
    keycloak_url = f"{issuer_parsed.scheme}://{issuer_parsed.netloc}/"
    client_id = oidc.client_id
    client_secret = oidc.client_secret
    if not client_id or not client_secret:
        logger.error("OIDC client_id or client_secret not set")
        return False
    access_token = get_client_access_token(
        keycloak_url, realm, client_id, client_secret
    )
    if access_token is None:
        logger.error("Could not get access token from Keycloak with OIDC settings")
        return False
    if _check_redirect_uris(client_id, access_token) is False:
        logger.error("Redirect URIs in Keycloak do not match OIDC settings")
        return False
    return True


def varenvs_exist() -> bool:
    """Check if all required environment variables are set."""
    required_vars = [
        "keycloak_admin_user",
        "keycloak_admin_password",
        "keycloak_url",
        "keycloak_client_id",
        "keycloak_client_secret",
        "keycloak_issuer",
        "keycloak_redirect_uris",
        "keycloak_realm",
    ]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        return False
    return True


def get_objects_from_catalog():
    catalog = api.portal.get_tool("portal_catalog")
    brains = catalog(sort_on="path")
    objects = []
    for brain in brains:
        try:
            obj = brain.getObject()
            objects.append(obj)
        except Exception as e:
            logger.info(f"Error getting object from brain {brain}: {e}")
            continue
    objects.insert(0, api.portal.get())
    return objects


def get_list_local_roles():
    avoided_roles = ["Owner"]
    acl = api.portal.get_tool("acl_users")
    objects = get_objects_from_catalog()
    olr = []
    for ob in objects:
        for username, roles, userType, userid in acl._getLocalRolesForDisplay(ob):
            roles = [role for role in roles if role not in avoided_roles]
            if roles:
                if ob not in olr:
                    olr.append(ob)
    return olr


def get_keycloak_users_from_oidc():
    """Get Keycloak users using client credentials authentication.

    Returns a list of dictionaries containing username and email for each user.
    Uses keycloak_client_id and keycloak_client_secret environment variables.
    """
    realm = os.environ.get("keycloak_realm", "plone")
    keycloak_url = os.environ.get("keycloak_url")

    if not keycloak_url:
        logger.error("Missing keycloak_url environment variable")
        return []

    # Get access token using client credentials
    access_token = get_client_access_token()
    if not access_token:
        logger.error("Could not get client access token from Keycloak")
        return []

    # Fetch users from Keycloak
    # Get all users from the "iA.Smartweb" group in the realm
    oidc = get_plugin()
    group_names = oidc.allowed_groups
    # group_name = "iA.Smartweb"
    group_url = f"{keycloak_url}admin/realms/{realm}/groups"
    group_response = requests.get(
        url=group_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30
    )
    group_response.raise_for_status()
    groups = group_response.json()
    group_ids = []
    for group in groups:
        if group.get("name") in group_names:
            group_ids.append(group.get("id"))
    if not group_ids:
        logger.error(f"Groups '{group_names}' not found in Keycloak realm '{realm}'")
        return []

    users = []
    headers = {"Authorization": f"Bearer {access_token}"}
    for group_id in group_ids:
        url = f"{keycloak_url}admin/realms/{realm}/groups/{group_id}/members?max=100000"
        try:
            response = requests.get(url=url, headers=headers, timeout=30)
            response.raise_for_status()
            users_data = response.json()

            # Extract username and email from each user
            for user in users_data:
                user_info = {
                    "username": user.get("username", ""),
                    "email": user.get("email", ""),
                    "keycloak_id": user.get("id", ""),
                    "firstName": user.get("firstName", ""),
                    "lastName": user.get("lastName", ""),
                }
                # Only include users that have both username and email
                if user_info["username"] and user_info["email"]:
                    users.append(user_info)

            logger.info(f"Retrieved {len(users)} users from Keycloak realm '{realm}'")
            return users

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching users from Keycloak: {e}")
            return []
        except ValueError as e:
            logger.error(f"Error parsing users response: {e}")
            return []


def add_keycloak_users_to_plone(users):
    """Add Keycloak users to Plone if they do not already exist."""
    oidc = get_plugin()
    users_added = 0

    for user in users:
        username = user.get("username")
        email = user.get("email")
        keycloak_id = user.get("keycloak_id")

        if not username or not email or not keycloak_id:
            logger.warning(f"Skipping user with missing username or email: {user}")
            continue

        existing_user = api.user.get(username=username)
        if existing_user:
            logger.info(f"User '{username}' already exists in Plone. Skipping.")
            continue

        try:
            new_user = oidc._create_user(keycloak_id)
            if new_user is None:
                logger.error(f"Failed to create user '{username}' in OIDC plugin.")
                continue

            userinfo = {
                "username": username,
                "email": email,
                "given_name": user.get("firstName", ""),
                "family_name": user.get("lastName", ""),
            }
            oidc._update_user(new_user, userinfo, first_login=True)
            users_added += 1
            logger.info(f"Added new user '{username}' to Plone.")

        except Exception as e:
            logger.error(f"Error adding user '{username}': {e}")
            continue

    logger.info(f"Total new users added to Plone: {users_added}")
    return users_added


def remove_authentic_users(context=None) -> None:
    """Remove all users from the authentic plugin, except those with 'iateleservices' in their username."""
    acl_users = api.portal.get_tool("acl_users")
    authentic = acl_users.get("authentic", None)
    if authentic is None:
        logger.error("No authentic plugin.")
        return
    portal_membership = api.portal.get_tool("portal_membership")
    users_to_delete = []
    authentic_users = authentic.getUsers()
    for user in authentic_users:
        username = api.user.get(user.getId()).getUserName()
        if "iateleservices" not in username:
            users_to_delete.append(user.getId())
            logger.info(
                f"{user.getProperty('email')} from authentic users will be deleted."
            )
        else:
            logger.info(f"{username} from authentic users will be kept.")
    logger.info(f"Total authentic users to delete: {len(users_to_delete)}")
    logger.info(
        f"Total authentic users kept: {len(authentic_users) - len(users_to_delete)}"
    )
    portal_membership.deleteMembers(users_to_delete, delete_localroles=0)
    transaction.commit()
