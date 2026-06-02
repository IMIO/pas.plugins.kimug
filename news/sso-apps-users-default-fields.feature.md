`get_keycloak_users_from_oidc_sso_apps` now includes SSO apps users that are missing optional fields:
missing email is filled as `{username}@kimug.be`; missing first and last name are filled as the username and `sso-apps` respectively.
[remdub]
