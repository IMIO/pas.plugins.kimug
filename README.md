# pas.plugins.kimug

A PAS plugin to set roles to imio keycloak users

Kimug is a acronym for "Keycloak IMio User & Group"

## Documentation

Full documentation, with architecture and authentication-flow diagrams, is in [docs/kimug.md](docs/kimug.md).

## Installation

### Install pas.plugins.kimug:

Requires [uv](https://docs.astral.sh/uv/). This installs Plone 6.2.3 in `.venv`
(use `PLONE_VERSION=6.1.6 make install` for another version):

```shell
make install
```

### Create the Plone site:

```shell
make create-site
```

## Test / dev environment

### Init dev environment

You have to initialize a certificate with `tests/mkcert.sh` .


### Start dev environment

```shell
make docker-start
```

This command will start a keycloak instance available at https://keycloak.127.0.0.1.nip.io


### Tests dev accounts

| Realm    | login | e-mail        | password |
| ---------| ----- | --------------| -------- |
| master   | admin |               | admin    |
| imio     | kimug | kimug_at_imio.be | kimug    |
| plone    | plone | plone_at_imio.be | plone    |
| sso-apps | imio-apps-plone_belleville-ac | imio-apps_at_kimug.be | Kimug123456*** |

### Export keycloak realms

```shell
cd tests
docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-imio.json --realm imio
docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-plone.json --realm plone
docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-sso-apps.json --realm sso-apps
```

### Run test

Tests start Keycloak themselves through Docker (pytest-docker).

```shell
.venv/bin/pytest tests -s
```

or only one class

```shell
.venv/bin/pytest tests -s -k TestMigration
```

Through tox, as the CI does (`make test-all` runs every Plone / Python combination):

```shell
make test
uvx --with tox-uv tox -e py312-plone61
```

### Lint

```shell
make check
```

## Contribute

- [Issue Tracker](https://github.com/imio/pas.plugins.kimug/issues)
- [Source Code](https://github.com/imio/pas.plugins.kimug/)

## License

The project is licensed under GPLv2.
