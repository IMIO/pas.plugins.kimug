## 1.9.3 (unreleased)


- Fix OIDC login crash when a Keycloak group name collides with an
  existing Plone user id (e.g. the `imio` IdP-link alias): skip the unmappable
  group instead of dereferencing `None` in `_create_update_groups`. [remdub]


## 1.9.2 (2026-07-09)


- Handle quoted list elements in puppet-rendered group env vars.
  (erb templates returns us quoted list elements)
  [remdub]


## 1.9.1 (2026-07-09)


- Remove deprecated `keycloak_redirect_uris` from the required env vars checked
  by `varenvs_exist` (dead since 1.3.0, code purged in 1.4.0). [remdub]


## 1.9.0 (2026-07-08)


### New features:

- Make the install-time user migration app-agnostic, driven by the `application_id` environment variable. A new `run_user_migration` helper selects which extra Keycloak realms to fetch and whether to clean up the legacy `authentic` plugin (via `APP_MIGRATION_CONFIG`), so apps with plain Plone users (e.g. `iA.Bibliotheca`) are migrated by email without the `iA.Smartweb`-specific `imio` realm fetch or `authentic` cleanup. [remdub] app-agnostic-migration


## 1.8.0 (2026-06-23)


### New features:

- Add Kimug Authenticated Users role and grant it to plugin-created users
  (new users on creation, existing users via the 1006→1007 upgrade step).
  [boulch, remdub]


## 1.7.2 (2026-06-18)


- Add reviewer roles to sso-apps users
  [remdub]


## 1.7.1 (2026-06-18)


### Bug fixes:

- Send an explicit `User-Agent` header when fetching Keycloak's JWKS: PyJWT's
  `PyJWKClient` defaults to `Python-urllib/<ver>`, which the production Keycloak
  WAF rejects with `403 Forbidden`, breaking Bearer-token verification. Each
  JWKS client is now built with `User-Agent: pas.plugins.kimug`. [bsuttor]


## 1.7.0 (2026-06-17)


### New features:

- Remove pas.plugins.imio and authentic plugin
  [remdub]

- Restrict the SSO-apps user sync to members of an organisation-specific municipality group: `get_keycloak_users_from_oidc_sso_apps` now only imports access-group members that also belong to one of the groups listed in the `SSO_APPS_MUNICIPALITY_GROUPS` environment variable (e.g. `[pl_belleville_ac]`). When the variable is unset, all access-group members are imported as before. [remdub]

- Browser view (with run and dry-run buttons in the control panel) and thin `scripts/set_sso_apps_permissions.py` runscript to set roles on authentic sources from sso apps. [remdub]


### Bug fixes:

- Fix sticky `403 Forbidden` on token authentication: the JWKS signing-key client was a single class-level cache shared by both the `oidc` and `sso-apps` realms. A request would receive a client built for the other realm, whose `kid` is never in the cached keyset, forcing a live JWKS refetch on essentially every request. That fetch storm could trip the Keycloak proxy's rate-limiter into returning 403, and PyJWT clearing its keyset cache on each failed fetch kept it failing until a restart. JWKS clients are now cached per realm. [remdub]
- Add a per-realm JWKS failure backoff: after a failed signing-key fetch, further fetches for that realm are skipped for a short cooldown, so a transient 403 from the Keycloak proxy can no longer become a self-sustaining retry storm. Authentication for the realm recovers automatically once the endpoint is healthy again, without a restart. [remdub]


## 1.6.3 (2026-06-09)


### Bug fixes:

- Fix auto-created SSO users having no email or name: `_ensure_user_exists` was reading Keycloak Admin-API field names (`username`, `firstName`, `lastName`, `id`) from the JWT, but tokens carry OIDC claim names (`preferred_username`, `given_name`, `family_name`, `sub`). User properties are now populated from the correct claims, and the `{username}@kimug.be` fallback works again.
  [remdub] ensure-user-claims


## 1.6.2 (2026-06-09)


### Bug fixes:

- Don't crash startup when the `pas.plugins.kimug.log` registry record is missing on a not-yet-upgraded site. The `set_oidc_settings` subscriber now skips writing the record when it isn't registered, instead of raising `InvalidParameterError` and preventing the instance from booting.
  [remdub] log-record-boot-fix


## 1.6.1 (2026-06-08)


### Bug fixes:

- Make the `oidc` plugin handle the interactive login challenge instead of `oidc_sso_apps`. The `oidc_sso_apps` plugin is now removed from `IChallengePlugin` (it only validates Bearer tokens), and upgrade step 1004→1005 fixes already-installed sites.
  [remdub] oidc-first-challenge


## 1.6.0 (2026-06-05)


### New features:

- Refactor the control panel so SSO applications (apps) settings can be configured easily. [remdub] controlpanel-sso-apps


### Bug fixes:

- Fix control panel action buttons (update OIDC settings, sync Keycloak users) being blocked by plone.protect CSRF protection, which aborted the transaction and redirected to the "Confirming User Action" page. The buttons now include a valid `_authenticator` token. [remdub] controlpanel-csrf


## 1.5.5 (2026-06-04)


### New features:

- When creating a new user from an `oidc_sso_apps` token, missing `email` is defaulted to `{username}@kimug.be` and missing `firstName`/`lastName` are defaulted to `{username}` / `"sso-apps"`.
  [remdub] sso-apps-user-defaults
- `_decode_token` for `oidc_sso_apps` now reads the JWT audience from `SSO_APPS_AUDIENCE` env var, falling back to `SSO_APPS_CLIENT_ID` and then `"imio-apps-plone"`.
  [remdub] token-audience


## 1.5.4 (2026-06-04)


### New features:

- Set log level to info for pas.plugins.kimug logger
  [remdub]


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
