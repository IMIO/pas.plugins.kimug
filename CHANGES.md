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
