from pas.plugins.kimug import utils


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
        assert sanitized_uris is None
