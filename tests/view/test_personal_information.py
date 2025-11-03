from plone import api
from zope.component import getMultiAdapter

import pytest


class TestNewUserView:
    @pytest.fixture(autouse=True)
    def _init(self, portal, http_request):
        with api.env.adopt_roles(
            [
                "Manager",
            ]
        ):
            self.portal = portal
            self.request = http_request
            view = getMultiAdapter(
                (self.portal, self.request), name="personal-information"
            )
            self.view = view

    def test_redirect(self):
        """Test the redirect after going to personal information."""
        self.view()
        assert self.view.request.response.status == 302
        assert (
            self.view.request.response.headers["location"]
            == "http://kamoulox.be/personal_info"
        )
