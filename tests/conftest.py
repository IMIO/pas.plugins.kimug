from pas.plugins.kimug.testing import ACCEPTANCE_TESTING
from pas.plugins.kimug.testing import FUNCTIONAL_TESTING
from pas.plugins.kimug.testing import INTEGRATION_TESTING
from pathlib import Path
from plone import api
from pytest_plone import fixtures_factory
from requests.exceptions import ConnectionError
from zope.component.hooks import setSite

import pytest
import requests


pytest_plugins = ["pytest_plone"]


globals().update(
    fixtures_factory(
        (
            (ACCEPTANCE_TESTING, "acceptance"),
            (FUNCTIONAL_TESTING, "functional"),
            (INTEGRATION_TESTING, "integration"),
        )
    )
)


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    """Fixture pointing to the docker-compose file to be used."""
    return Path(str(pytestconfig.rootdir)).resolve() / "tests" / "docker-compose.yml"


def is_responsive(url: str) -> bool:
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return True
    except ConnectionError:
        return False


@pytest.fixture(scope="session")
def keycloak_service(docker_ip, docker_services):
    """Ensure that keycloak service is up and responsive."""
    # `port_for` takes a container port and returns the corresponding host port
    port = docker_services.port_for("keycloak", 8080)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=60.0, pause=0.1, check=lambda: is_responsive(url)
    )
    return url


@pytest.fixture(scope="session")
def keycloak(keycloak_service):
    return {
        "issuer": f"{keycloak_service}/realms/imio",
        "client_id": "plone",
        "client_secret": "12345678910",  # nosec B105
        "scope": ("openid", "profile", "email"),
    }


@pytest.fixture(scope="session")
def keycloak_api(keycloak_service):
    return {
        "enabled": True,
        "server_url": keycloak_service,
        "realm_name": "plone-test",
        "client_id": "plone-admin",
        "client_secret": "12345678",  # nosec B105
    }


@pytest.fixture
def wait_for():
    def func(thread):
        if not thread:
            return
        thread.join()

    return func


@pytest.fixture()
def portal(integration, keycloak, keycloak_api):
    portal = integration["portal"]
    setSite(portal)
    plugin = portal.acl_users.oidc
    with api.env.adopt_roles(["Manager", "Member"]):
        for key, value in keycloak.items():
            setattr(plugin, key, value)
        # for key, value in keycloak_api.items():
        #     name = f"keycloak_groups.{key}"
        #     api.portal.set_registry_record(name, value)
    return portal
