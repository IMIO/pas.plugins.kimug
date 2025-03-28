# pas.plugins.kimug

A PAS plugin to set roles to imio keycloak users

## Features

TODO: List our awesome features

## Installation

Install pas.plugins.kimug with `pip`:

```shell
pip install pas.plugins.kimug
```

And to create the Plone site:

```shell
make build
make create-site
```

## Add features using `plonecli` or `bobtemplates.plone`

This package provides markers as strings (`<!-- extra stuff goes here -->`) that are compatible with [`plonecli`](https://github.com/plone/plonecli) and [`bobtemplates.plone`](https://github.com/plone/bobtemplates.plone).
These markers act as hooks to add all kinds of subtemplates, including behaviors, control panels, upgrade steps, or other subtemplates from `plonecli`.

To run `plonecli` with configuration to target this package, run the following command.

```shell
make add <template_name>
```

For example, you can add a content type to your package with the following command.

```shell
make add content_type
```

You can add a behavior with the following command.

```shell
make add behavior
```

```{seealso}
You can check the list of available subtemplates in the [`bobtemplates.plone` `README.md` file](https://github.com/plone/bobtemplates.plone/?tab=readme-ov-file#provided-subtemplates).
See also the documentation of [Mockup and Patternslib](https://6.docs.plone.org/classic-ui/mockup.html) for how to build the UI toolkit for Classic UI.
```

## Test environment

### export imio realm

```shell
cd tests && docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-imio.json --realm imio

docker compose exec keycloak /opt/keycloak/bin/kc.sh export --file /opt/keycloak/data/import/realm-plone.json --realm ploneq
```

### Tests credentials

- login : kimug

- email : kimug@imio.be

- password : kimug

### Run test

```shell
.venv/bin/tox -e test -s
```

## Contribute

- [Issue Tracker](https://github.com/imio/pas.plugins.kimug/issues)
- [Source Code](https://github.com/imio/pas.plugins.kimug/)

## License

The project is licensed under GPLv2.

## Credits and Acknowledgements 🙏

Generated using [Cookieplone (0.8.3)](https://github.com/plone/cookieplone) and [cookiecutter-plone (d23b89f)](https://github.com/plone/cookiecutter-plone/commit/d23b89fb29648aa2bb85d39324cd3d226fff3ac3) on 2025-02-18 13:33:21.819251. A special thanks to all contributors and supporters!
