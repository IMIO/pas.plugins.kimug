## 1.5.3 (2026-06-03)


### New features:

- Add ``is_log_active`` utility function to check if plugin logging is enabled via the registry. [remdub] is-log-active

## 1.5.2 (2026-06-02)


### New features:

- `get_keycloak_users_from_oidc_sso_apps` now includes SSO apps users that are missing optional fields:
  missing email is filled as `{username}@kimug.be`; missing first and last name are filled as the username and `sso-apps` respectively.
  [remdub] sso-apps-users-default-fields



## 1.5.1 (2026-06-02)


### New features:

- Add upgrade step (1002→1003) that registers the `oidc_sso_apps` plugin, applies OIDC settings, and syncs SSO Apps users from Keycloak into Plone on existing instances.
  [remdub] upgrade-1003-oidc-sso-apps



## 1.5.0 (2026-05-29)


### New features:

- Add SSO apps authentication via a second PAS plugin (`oidc_sso_apps`) backed by a dedicated `sso-apps` Keycloak realm.
  Bearer tokens are routed to the correct plugin by inspecting the `iss` claim; Plone users are created automatically on first access.
  A sync view (`/keycloak_sso_apps_users`) lets administrators bulk-import SSO app users. Configure via `SSO_APPS_CLIENT_ID`, `SSO_APPS_CLIENT_SECRET`, `SSO_APPS_URL`, `SSO_APPS_ACCESS_GROUP`.
  [remdub] sso-apps-authentication


### Bug fixes:

- **Security:** Kimug bearer-token authentication now verifies JWT signatures
  against the Keycloak realm's JWKS with RS256, and checks `iss`, `aud`,
  `exp`, `iat`. Previously `jwt.decode(..., options={"verify_signature": False})`
  accepted any JWT — including attacker-forged tokens — allowing account
  takeover by sending `Authorization: Bearer <unsigned.jwt>`. `_decode_token`
  now returns `None` on any verification failure instead of raising, so the
  PAS authentication chain degrades cleanly.
  Configure `keycloak_url`, `keycloak_realm`, `keycloak_issuer` and
  `keycloak_audience` via environment variables (audience defaults to
  `account`).
  [bsuttor] kimug-jwt-verify


## 1.4.3 (2026-03-24)


- DEVOPS-339 : Fix ConflictError when multiple Zope instances start simultaneously and commit OIDC settings
  [remdub]


## 1.4.2 (2025-12-10)

- Set administrator role for users in group iA.Smartweb-admin with an imio address.
  [bsuttor]


## 1.4.1 (2025-11-25)

- WEB-4331 : Set Allowed Groups with environment variable
  [remdub]


## 1.4.0 (2025-11-04)

- Upgrade dev environment to Plone 6.1.3
  [remdub]

- Override views related to user management
  We no longer create or modify users in Plone
  This is now handled by Keycloak
  [remdub]

- Remove deprecated methods related to redirect uris
  We are not using those methods anymore since 1.3.0
  [remdub]


## 1.3.1 (2025-09-30)

- Do not gave administrator role for users in group iA.Smartweb.
  [bsuttor]


## 1.3.0 (2025-09-25)

- Skip OIDC settings configuration when Plone site or OIDC plugin is unavailable
  [remdub]

- Set "came_from" session variable from HTTP_REFERER instead of came_from request.
  [bsuttor]

- In controlpanel status, check if the redirect_uris set in Keycloak match the ones set in the OIDC plugin.
  [remdub]

- Set OIDC settings from environment variables on instance boot
  [remdub, bsuttor]


## 1.2.0 (2025-09-16)

- Add controlpanel
  [remdub]

- Add a view to set OIDC settings
  [remdub]

- Add a view to import Keycloak users to Plone.
  [bsuttor]


## 1.1.5 (2025-09-09)


- Add upgrade-step to clean authentic users
  [remdub]


## 1.1.4 (2025-08-28)


- You should rerun migration as many times as you want.
  [bsuttor]


## 1.1.3 (2025-08-28)


- Check if realm exists and environment variables are set before migration
  [remdub]


## 1.1.2 (2025-08-27)


- Add forgot local roles on migration to Keycloak.
  [bsuttor & remdub]

## 1.1.1 (2025-08-26)


- Migrate users form Authentic to Keycloal OIDC plugin.
  [bsuttor]


## 1.1.0 (2025-07-10)


- Migrate authentic to keycloak


## 1.0.0 (2025-03-31)
