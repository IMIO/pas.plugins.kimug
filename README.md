# pas.plugins.kimug

A PAS plugin to set roles to imio keycloak users

Kimug is a acronym for "Keycloak IMio User & Group"

## Installation

### Install pas.plugins.kimug:

```shell
make build
```

### Create the Plone site:

```shell
make create-site
```

## Test environment

### export imio realm

```shell
cd tests && docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-imio.json --realm imio

docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-plone.json --realm plone
```

### Tests credentials

- login : kimug

- email : kimug@imio.be

- password : kimug

### Run test

```shell
.venv/bin/tox -e test -s
```

or only one class

```shell
.venv/bin/pytest tests -s -k TestMigration
```

## Contribute

- [Issue Tracker](https://github.com/imio/pas.plugins.kimug/issues)
- [Source Code](https://github.com/imio/pas.plugins.kimug/)

## License

The project is licensed under GPLv2.
