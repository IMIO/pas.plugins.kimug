# CLAUDE.md — pas.plugins.kimug

Plone PAS plugin that authenticates iMio Keycloak users ("Wallonie Connect" SSO) and assigns them roles. Extends `pas.plugins.oidc`. Full documentation with flow diagrams: `docs/kimug.md`.

## Build & Run

```bash
make build          # Install Plone (aliases: install, all)
make config         # Create instance configuration
make create-site    # Create a new Plone site
make start          # Start Plone on localhost:8080
```

## Testing

Tests require a Docker Keycloak instance (managed by pytest-docker via `tests/docker-compose.yml`): Keycloak + PostgreSQL behind Traefik at `https://keycloak.127.0.0.1.nip.io/`, with three realms imported (`plone`, `imio`, `sso-apps`).

```bash
.venv/bin/pytest tests -s          # Run the test suite (preferred)
make test                          # Same via tox (tox -e test)
tox -e test -- tests/plugin/       # Run a specific test directory
tox -e test -- -k test_name        # Run a single test by name
tox -e coverage                    # Tests with coverage report
```

Test credentials: master admin `admin`/`admin`; OIDC user `kimug` / password `kimug` / email `kimug@imio.be`; SSO-apps user `imio-apps-plone_belleville-ac`.

Keycloak test fixtures in `tests/conftest.py`:
- `keycloak_service` — waits for the JWKS endpoint to answer before tests start
- `keycloak` — session fixture (issuer, client_id `plone`, client_secret `12345678910`)
- `keycloak_api` — admin API fixture (realm `plone-test`, client `plone-admin`, secret `12345678`)
- `portal` — integration portal with the plugins installed and configured

## Linting & Formatting

```bash
make check       # Lint (runs tox -e lint → pre-commit)
tox -e format    # Auto-format (pyupgrade, isort, black, zpretty)
```

Pre-commit tools: pyupgrade, isort, black, zpretty, flake8, codespell, check-manifest, pyroma, i18ndude.

## Architecture

### Plugins

The package installs **two instances** of the same `KimugPlugin` class (in `src/pas/plugins/kimug/plugin/__init__.py`, extends `OIDCPlugin` from `pas.plugins.oidc`) in `acl_users`:

| Plugin id | Purpose |
|---|---|
| `oidc` | Interactive browser login through the main Keycloak realm (Authorization Code flow with PKCE). Handles the `IChallengePlugin` redirect to Keycloak. |
| `oidc_sso_apps` | Stateless Bearer-token validation for machine-to-machine calls from other iMio applications (`sso-apps` realm). Its `IChallengePlugin` activation is deliberately removed so it never hijacks the interactive login. |

PAS interfaces implemented:
- `IExtractionPlugin` — extracts `Authorization: Bearer <JWT>` tokens (RFC 6750)
- `IAuthenticationPlugin` — fully verifies the JWT (RS256 signature against Keycloak's JWKS, issuer, audience, expiry) and routes it to the right plugin based on the token's `iss` claim; `sso-apps` tokens additionally require membership in `SSO_APPS_ACCESS_GROUP`; auto-creates Plone users on first Bearer login (`_ensure_user_exists`)
- `IRolesPlugin` — assigns `Member` to all; adds `Manager` if user is in `{application_id}-admin` group AND has `@imio.be` email
- `IChallengePlugin` — redirects to Keycloak login (active on `oidc` only)

JWKS caching (class-level on `KimugPlugin`): one `PyJWKClient` per plugin id, rebuilt after `_JWKS_CLIENT_TTL` (3600 s) to pick up key rotations, plus a `_JWKS_FAILURE_COOLDOWN` (30 s) backoff after failed fetches. Verification failures return `None` (PAS falls through), never HTTP 500.

### Key Modules

| Path | Purpose |
|------|---------|
| `plugin/__init__.py` | `KimugPlugin` class: token extraction, JWT verification, JWKS caching, role assignment, user auto-creation |
| `utils.py` | Keycloak admin REST API integration, user sync/migration, `set_oidc_settings` startup configuration, settings validation |
| `browser/view.py` | Login/callback views and admin views (migration, user sync, `@@set_oidc_settings`, debug toggle, Keycloak-hosted redirects for new-user/personal-information/change-password) |
| `controlpanel/classic.py` | Control panel adapter and forms for both plugin instances (`@@kimug-controlpanel`) |
| `interfaces.py` | `IBrowserLayer`, `IKimugPlugin`, `IKimugSettings`, `IKimugSSOAppsSettings` |
| `setuphandlers/__init__.py` | `post_install` handler: creates both plugins, applies settings, runs migration |
| `subscribers/configure.zcml` | Registers `set_oidc_settings` on `IDatabaseOpenedWithRoot` (Zope startup) |
| `upgrades/` | GenericSetup upgrade steps (profile versions 1000 → 1005) |
| `testing.py` | INTEGRATION_TESTING, FUNCTIONAL_TESTING, ACCEPTANCE_TESTING layers |

### Environment Variables

All configuration is environment-driven (set by puppet in production) and applied at Zope startup by the `set_oidc_settings` subscriber. List-valued variables use bracket format: `[group1, group2]` (comma-separated also works).

**`oidc` plugin (interactive login):**

- `WEBSITE_HOSTNAME` — builds the redirect URI `https://{hostname}/acl_users/oidc/callback`
- `keycloak_url`, `keycloak_realm` (default: `plone`), `keycloak_issuer`
- `keycloak_client_id` (default: `plone`), `keycloak_client_secret` (default: `12345678910`)
- `keycloak_audience` (default: `account`) — expected `aud` claim for Bearer tokens
- `keycloak_admin_user`, `keycloak_admin_password` — for Keycloak admin API (migration, full user fetch)
- `keycloak_allowed_groups` — groups allowed to log in / be synced
- `keycloak_add_user_url`, `keycloak_personal_information_url`, `keycloak_change_password_url` — Keycloak-hosted redirect targets
- `application_id` (default: `iA.Smartweb`) — admin group prefix for the `Manager` role (`{application_id}-admin`)
- `KIMUG_LOG` — when not `true`, the debug logging registry record is forced off at startup

**`oidc_sso_apps` plugin (Bearer tokens from other iMio apps):**

- `SSO_APPS_URL` (default: `https://keycloak.127.0.0.1.nip.io/realms/sso-apps`) — issuer URL
- `SSO_APPS_REALM` (default: `sso-apps`) — realm for JWKS and issuer derivation
- `SSO_APPS_CLIENT_ID` (default: `imio-apps-plone`), `SSO_APPS_CLIENT_SECRET`
- `SSO_APPS_AUDIENCE` — expected `aud` claim (falls back to `SSO_APPS_CLIENT_ID`)
- `SSO_APPS_ACCESS_GROUP` (default: `access_imio-apps-kimug`) — Keycloak group required to authenticate via sso-apps tokens
- `SSO_APPS_MUNICIPALITY_GROUPS` — restricts the SSO-apps user sync to members of these municipality groups (unset = no filtering)

### GenericSetup

- Default profile at `profiles/default/` (version **1005**)
- Uninstall profile at `profiles/uninstall/`
- Upgrade steps in `upgrades/` (1000 → 1005)
- `post_install` creates both plugins (`oidc_sso_apps` without `IChallengePlugin`), runs `set_oidc_settings`, and if the required env vars are present runs the user-id migration

## Key Patterns

- **Namespace packages**: `pas` and `pas.plugins` are namespace packages (`setup.py`)
- **ZCML registration**: `five:registerPackage` with `initialize` function; browser pages, subscribers, controlpanel registered via ZCML includes
- **z3c.autoinclude**: Plugin auto-discovered by Plone via entry point
- **Testing layers**: `PloneSandboxLayer` + `PLONE_APP_CONTENTTYPES_FIXTURE`; pytest-plone fixtures; pytest-docker for Keycloak
- **Dependencies**: `pas.plugins.oidc>=2.0.0b4`, `python-keycloak`, `PyJWT[crypto]>=2.6`, `plone.api`
- Python ≥ 3.10, Plone 6.0/6.1, GPLv2
