# from pas.plugins.kimug.utils import get_keycloak_users
# from pas.plugins.kimug.utils import migrate_plone_user_id_to_keycloak_user_id
# from plone import api
# from plone.app.testing import login
# from plone.app.testing import logout
# from plone.app.testing import SITE_OWNER_NAME

# import json
# import os
# import requests


# def access_token(keycloak_url):
#     url = f"{keycloak_url}realms/master/protocol/openid-connect/token"
#     payload = {
#         "client_id": "admin-cli",
#         "username": "admin",
#         "password": "admin",
#         "grant_type": "password",
#     }
#     headers = {"Content-Type": "application/x-www-form-urlencoded"}
#     response = requests.post(url=url, headers=headers, data=payload)
#     access_token = response.json()["access_token"]
#     return access_token


# def create_keycloak_user(keycloak_url, access_token, realm, payload):
#     """Create a user in Keycloak."""
#     url = f"{keycloak_url}admin/realms/{realm}/users"
#     headers = {
#         "Authorization": "Bearer " + access_token,
#         "Content-type": "application/json",
#     }
#     response = requests.post(url=url, headers=headers, data=json.dumps(payload))
#     if response.status_code == 201:
#         print(f"User {payload['username']} created successfully.")
#     elif response.status_code == 409:
#         print(f"User {payload['username']} already exists.")
#     else:
#         print(
#             f"Failed to create user {payload['username']}: {response.status_code} - {response.text}"
#         )


# def get_keycloak_local_users(keycloak_url, token, realm):
#     url = f"{keycloak_url}admin/realms/{realm}/users"
#     headers = {"Authorization": "Bearer " + token}
#     response = requests.get(url=url, headers=headers)
#     if response.status_code == 200 and response.json():
#         return response.json()  # Return all users of realm
#     else:
#         print(f"User with email {token} not found in realm {realm}.")
#         return None


# def create_plone_user(user_id, username, email):
#     """Create a user in Plone."""
#     roles = ("Member",)
#     properties = {}
#     registration = api.portal.get_tool("portal_registration")
#     properties.update(username=username)
#     properties.update(email=email)
#     registration.addMember(
#         user_id,
#         "password",
#         roles,
#         properties=properties,
#     )
#     return api.user.get(userid=user_id)


# def init_test_users(portal, keycloak_url, token):
#     """Initialize test users in Plone."""
#     all_kc_user_from_plone = get_keycloak_local_users(
#         keycloak_url,
#         token,
#         "plone",
#     )
#     assert len(all_kc_user_from_plone) == 1
#     test_users = [
#         {
#             "keycload_id": "",
#             "plone_id": "plone_id_1",
#             "username": "plone_id_1",
#             "email": "plone_id_1@kimug.be",
#             "enabled": True,
#             "emailVerified": True,
#             "firstName": "Plone",
#             "lastName": "1",
#         },
#         {
#             "keycload_id": "",
#             "plone_id": "plone_id_2",
#             "username": "plone_id_2",
#             "email": "plone_id_2@kimug.be",
#             "enabled": True,
#             "emailVerified": True,
#             "firstName": "Plone",
#             "lastName": "2",
#         },
#         {
#             "keycload_id": "",
#             "plone_id": "plone_id_3",
#             "username": "plone_id_3",
#             "email": "plone_id_3@kimug.be",
#             "enabled": True,
#             "emailVerified": True,
#             "firstName": "Plone",
#             "lastName": "3",
#         },
#     ]
#     plone_users = []
#     for i, test_user in enumerate(test_users):
#         # Create user in Keycloak
#         payload = {
#             "username": test_user["username"],
#             "enabled": test_user["enabled"],
#             "emailVerified": test_user["emailVerified"],
#             "firstName": test_user["firstName"],
#             "lastName": test_user["lastName"],
#             "email": test_user["email"],
#         }

#         test_users[i]["keycload_id"] = create_keycloak_user(
#             keycloak_url,
#             token,
#             "plone",
#             payload,
#         )
#         # Create user in Plone
#         plone_users.append(
#             create_plone_user(
#                 test_user["plone_id"], test_user["username"], test_user["email"]
#             )
#         )
#     return test_users


# class TestMigration:
#     """Test migration view of pas.plugins.kimug."""

#     def test_migration_view(self, portal):
#         """Test active plugin of acl_users."""
#         keycloak_url = "http://keycloak.traefik.me/"
#         token = access_token(keycloak_url)
#         init_test_users(portal, keycloak_url, token)
#         all_kc_user_from_plone = get_keycloak_local_users(keycloak_url, token, "plone")
#         assert len(all_kc_user_from_plone) == 4
#         assert len(api.user.get_users()) == 4
#         assert (
#             api.user.get(userid="plone_id_2")._user.getProperty("email")
#             == "plone_id_2@kimug.be"
#         )

#         view = api.content.get_view(
#             "keycloak_migration",
#             portal,
#             portal.REQUEST,
#         )
#         view()
#         os.environ["keycloak_realms"] = "plone"
#         os.environ["keycloak_admin_user"] = "admin"
#         os.environ["keycloak_admin_password"] = "admin"
#         os.environ["keycloak_url"] = keycloak_url
#         users = get_keycloak_users()
#         assert len(users) == 4

#         # create content with a local plone user
#         api.user.grant_roles(username="plone_id_2", roles=["Site Administrator"])

#         logout()
#         login(portal, "plone_id_2")
#         api.content.create(
#             container=portal,
#             type="Document",
#             title="Test document",
#             id="test_document",
#         )
#         assert portal.test_document.title == "Test document"
#         assert portal.test_document.getOwner()._id == "plone_id_2"
#         assert portal.test_document.creators == ("plone_id_2",)
#         logout()

#         from Acquisition import aq_parent
#         from plone.testing import zope

#         app = aq_parent(portal)
#         zope.login(app["acl_users"], SITE_OWNER_NAME)
#         migrate_plone_user_id_to_keycloak_user_id(api.user.get_users(), users)
#         all_kc_user_from_plone = get_keycloak_local_users(keycloak_url, token, "plone")
#         kc_user_1_id = [
#             user["id"]
#             for user in all_kc_user_from_plone
#             if user["username"] == "plone_id_1"
#         ][0]
#         kc_user_2_id = [
#             user["id"]
#             for user in all_kc_user_from_plone
#             if user["username"] == "plone_id_2"
#         ][0]
#         assert api.user.get(userid=kc_user_1_id) != ""
#         assert (
#             api.user.get(userid=kc_user_2_id).getProperty("email")
#             == "plone_id_2@kimug.be"
#         )
#         assert portal.test_document.getOwner()._id == kc_user_2_id

#     def test_keycloak_users(self, portal):
#         pass

#     def test_dubble_email(self, portal):
#         pass

#     def test_groups(self, portal):
#         pass

#     def test_roles(self, portal):
#         pass
