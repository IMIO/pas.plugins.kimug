# CLAUDE.md — pas.plugins.kimug

Plone PAS plugin that assigns roles to iMio Keycloak users. Extends `pas.plugins.oidc`.

## Build & Run

```bash
make build          # Install Plone (aliases: install, all)
make config         # Create instance configuration
make create-site    # Create a new Plone site
make start          # Start Plone on localhost:8080
```

## Testing

Tests require a Docker Keycloak instance (managed by pytest-docker via `tests/docker-compose.yml`).

```bash
make test                          # Run full test suite (tox -e test)
tox -e test -- tests/plugin/       # Run a specific test directory
tox -e test -- -k test_name        # Run a single test by name
tox -e coverage                    # Tests with coverage report
```

Test credentials: user `kimug` / password `kimug` / email `kimug@imio.be`

Keycloak test fixtures in `tests/conftest.py`:
- `keycloak` — session fixture (issuer, client_id `plone`, client_secret `12345678910`)
- `keycloak_api` — admin API fixture (realm `plone-test`, client `plone-admin`, secret `12345678`)
- `portal` — integration portal with OIDC plugin configured

## Linting & Formatting

```bash
make check       # Lint (runs tox -e lint → pre-commit)
tox -e format    # Auto-format (pyupgrade, isort, black, zpretty)
```

Pre-commit tools: pyupgrade, isort, black, zpretty, flake8, codespell, check-manifest, pyroma, i18ndude.

## Architecture

### Plugin

`KimugPlugin` (in `src/pas/plugins/kimug/plugin/__init__.py`) extends `OIDCPlugin` from `pas.plugins.oidc` and implements:
- `IExtractionPlugin` — extracts Bearer token from Authorization header
- `IAuthenticationPlugin` — decodes JWT (currently without signature verification)
- `IRolesPlugin` — assigns `Member` to all; adds `Manager` if user is in `{application_id}-admin` group AND has `@imio.be` email
- `IChallengePlugin` — redirects to Keycloak login

### Key Modules

| Path | Purpose |
|------|---------|
| `plugin/__init__.py` | KimugPlugin PAS plugin class |
| `utils.py` | Keycloak API integration, JWKS, user migration, settings |
| `browser/view.py` | Views: Login, Callback, Migration, KeycloakUsers, NewUser, PersonalInformation, ChangePassword |
| `controlpanel/classic.py` | Control panel adapter and form |
| `setuphandlers/__init__.py` | GenericSetup post_install handler |
| `interfaces.py` | IBrowserLayer, IKimugPlugin, IKimugSettings |
| `testing.py` | INTEGRATION_TESTING, FUNCTIONAL_TESTING, ACCEPTANCE_TESTING layers |
| `subscribers/configure.zcml` | Calls `set_oidc_settings` on IDatabaseOpenedWithRoot |

### Environment Variables

Configuration is read from environment on Zope startup (`set_oidc_settings` subscriber):

- `WEBSITE_HOSTNAME` — hostname for redirect_uri
- `keycloak_url`, `keycloak_realm` (default: `plone`), `keycloak_issuer`
- `keycloak_client_id` (default: `plone`), `keycloak_client_secret` (default: `12345678910`)
- `keycloak_admin_user`, `keycloak_admin_password` — for Keycloak admin API
- `keycloak_allowed_groups` — comma-separated or `[group1, group2]`
- `keycloak_add_user_url`, `keycloak_personal_information_url`, `keycloak_change_password_url`
- `application_id` (default: `iA.Smartweb`) — used for admin group matching

### GenericSetup

- Default profile at `profiles/default/` (version 1002)
- Uninstall profile at `profiles/uninstall/`
- Upgrades in `upgrades/profiles/`

## Key Patterns

- **Namespace packages**: `pas` and `pas.plugins` are namespace packages (`setup.py`)
- **ZCML registration**: `five:registerPackage` with `initialize` function; browser pages, subscribers, controlpanel registered via ZCML includes
- **z3c.autoinclude**: Plugin auto-discovered by Plone via entry point
- **Testing layers**: `PloneSandboxLayer` + `PLONE_APP_CONTENTTYPES_FIXTURE`; pytest-plone fixtures; pytest-docker for Keycloak
- **Dependencies**: `pas.plugins.oidc>=2.0.0b4`, `python-keycloak`, `plone.api`
- Python ≥ 3.10, Plone 6.0/6.1, GPLv2
