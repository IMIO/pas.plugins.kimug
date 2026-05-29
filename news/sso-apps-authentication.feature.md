Add SSO apps authentication via a second PAS plugin (`oidc_sso_apps`) backed by a dedicated `sso-apps` Keycloak realm.
Bearer tokens are routed to the correct plugin by inspecting the `iss` claim; Plone users are created automatically on first access.
A sync view (`/keycloak_sso_apps_users`) lets administrators bulk-import SSO app users. Configure via `SSO_APPS_CLIENT_ID`, `SSO_APPS_CLIENT_SECRET`, `SSO_APPS_URL`, `SSO_APPS_ACCESS_GROUP`.
[remdub]
