from Acquisition import aq_base
from collections import defaultdict
from plone import api
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin
from zope.annotation.interfaces import IAnnotations

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
    oidc.userinfo_endpoint_method = "GET"

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
    response = requests.post(url=url, headers=headers, data=payload).json()
    if response.get("access_token", None) is None:
        logger.error(f"Error getting access token: {response}")
        # raise Exception("Could not get access token from Keycloak" "")
        return None
    access_token = response["access_token"]
    return access_token


def get_plugin():
    """Get the OIDC plugin."""
    pas = api.portal.get_tool("acl_users")
    oidc = pas.oidc
    return oidc


def get_keycloak_users():
    """Get all keycloak users."""
    realm = os.environ.get("keycloak_realm", None)
    # realms = os.environ.get("keycloak_realms", None)
    keycloak_url = os.environ.get("keycloak_url")
    keycloak_admin_user = os.environ.get("keycloak_admin_user")
    keycloak_admin_password = os.environ.get("keycloak_admin_password")
    access_token = get_admin_access_token(
        keycloak_url, keycloak_admin_user, keycloak_admin_password
    )
    if not access_token:
        logger.error("Could not get access token from Keycloak")
        return []
    # acl_users = api.portal.get_tool("acl_users")
    # oidc = acl_users.oidc
    # realm = oidc.issuer.split("/")[-1]
    kc_users = []
    # for realm in [r.strip() for r in realms.split(",")]:
    url = f"{keycloak_url}admin/realms/{realm}/users?max=100000"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url=url, headers=headers)
    if response.status_code == 200 and response.json():
        kc_users.extend(response.json())

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
            # logger.error(f"Error getting object from brain {brain}: {e}")
            continue
    objects.insert(0, api.portal.get())
    return objects


def get_list_local_roles():
    avoided_roles = ["Owner"]
    acl = api.portal.get_tool("acl_users")
    putils = api.portal.get_tool("plone_utils")
    objects = get_objects_from_catalog()
    olr = []
    for ob in objects:
        for username, roles, userType, userid in acl._getLocalRolesForDisplay(ob):
            roles = [role for role in roles if role not in avoided_roles]
            if roles:
                if ob not in olr:
                    olr.append(ob)
    return olr
