from pas.plugins.kimug import utils

import os


class TestUtils:
    def test_sanitize_redirect_uris(self):
        """Test sanitize_redirect_uris function."""

        good_sanitized_uris = (
            "http://url1",
            "http://url2",
            "http://url3",
        )

        redirect_uris = "('http://url1', 'http://url2', 'http://url3')"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = '("http://url1", "http://url2", "http://url3")'
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "['http://url1', 'http://url2', 'http://url3']"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = '["http://url1", "http://url2", "http://url3"]'
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "[http://url1, http://url2, http://url3]"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == good_sanitized_uris

        redirect_uris = "something else"
        sanitized_uris = utils.sanitize_redirect_uris(redirect_uris)
        assert sanitized_uris == ()

    def test_get_redirect_uris(self):
        """Test get_redirect_uris function."""

        current_redirect_uris = ()

        # 1 : no values set on oidc settings

        # Test with no environment variable set
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == ("http://localhost:8080/Plone/acl_users/oidc/callback",)

        # set website_hostname
        os.environ["website_hostname"] = "kimug.imio.be"
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)

        # set keycloak_redirect_uris
        os.environ["keycloak_redirect_uris"] = "['http://url1', 'http://url2']"
        redirect_uris = utils.get_redirect_uris(current_redirect_uris)
        assert redirect_uris == (
            "http://url1",
            "http://url2",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 2 : values set on oidc settings

        redirect_uris_from_oidc_settings = (
            "http://url1",
            "http://url2",
            "http://url3",
        )

        os.environ.pop("website_hostname", None)
        os.environ.pop("keycloak_redirect_uris", None)

        # Test with no environment variable set
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "http://localhost:8080/Plone/acl_users/oidc/callback",
        )
        # set website_hostname
        os.environ["website_hostname"] = "kimug.imio.be"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "https://kimug.imio.be/acl_users/oidc/callback",
        )
        # set keycloak_redirect_uris
        os.environ["keycloak_redirect_uris"] = "['http://url4', 'http://url5']"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == redirect_uris_from_oidc_settings + (
            "http://url4",
            "http://url5",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 3 : from preprod to prod

        os.environ["website_hostname"] = "kimug.imio.be"
        os.environ.pop("keycloak_redirect_uris", None)
        redirect_uris_from_oidc_settings = (
            "https://kimug.preprod.imio.be/acl_users/oidc/callback",
        )
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)

        os.environ["keycloak_redirect_uris"] = "[http://url1, http://url2]"
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == (
            "http://url1",
            "http://url2",
            "https://kimug.imio.be/acl_users/oidc/callback",
        )

        # 4 : uris already in the oidc settings

        os.environ["website_hostname"] = "kimug.imio.be"
        os.environ[
            "keycloak_redirect_uris"
        ] = "('https://kimug.imio.be/acl_users/oidc/callback',)"
        redirect_uris_from_oidc_settings = (
            "https://kimug.imio.be/acl_users/oidc/callback",
        )
        redirect_uris = utils.get_redirect_uris(redirect_uris_from_oidc_settings)
        assert redirect_uris == ("https://kimug.imio.be/acl_users/oidc/callback",)
