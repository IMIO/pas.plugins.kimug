Fix auto-created SSO users having no email or name: `_ensure_user_exists` was reading Keycloak Admin-API field names (`username`, `firstName`, `lastName`, `id`) from the JWT, but tokens carry OIDC claim names (`preferred_username`, `given_name`, `family_name`, `sub`). User properties are now populated from the correct claims, and the `{username}@kimug.be` fallback works again.
[remdub]
