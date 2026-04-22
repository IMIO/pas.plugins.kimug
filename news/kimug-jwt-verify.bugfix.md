**Security:** Kimug bearer-token authentication now verifies JWT signatures
against the Keycloak realm's JWKS with RS256, and checks `iss`, `aud`,
`exp`, `iat`. Previously `jwt.decode(..., options={"verify_signature": False})`
accepted any JWT — including attacker-forged tokens — allowing account
takeover by sending `Authorization: Bearer <unsigned.jwt>`. `_decode_token`
now returns `None` on any verification failure instead of raising, so the
PAS authentication chain degrades cleanly.
Configure `keycloak_url`, `keycloak_realm`, `keycloak_issuer` and
`keycloak_audience` via environment variables (audience defaults to
`account`).
[bsuttor]
