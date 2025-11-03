from bs4 import BeautifulSoup
from plone import api
from zope.component import getMultiAdapter

import pytest


class TestUsergroupUserPrefsView:
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
                (self.portal, self.request), name="usergroup-userprefs"
            )
            self.soup = BeautifulSoup(view(), "html.parser")

    def test_removed_columns(self):
        """Test the removed columns of the user groups overview."""
        table_userlisting = self.soup.find("table", summary="User Listing")
        headers = table_userlisting.find_all("th")
        """
        <th class="text-start">User name</th>,
        <th class="rotate"><div>Contributor</div></th>,
        <th class="rotate"><div>Editor</div></th>,
        <th class="rotate"><div>Member</div></th>,
        <th class="rotate"><div>Reader</div></th>,
        <th class="rotate"><div>Reviewer</div></th>,
        <th class="rotate"><div>Site Administrator</div></th>,
        <th class="rotate"><div>Manager</div></th>
        """
        assert len(headers) == 8
        expected_headers = [
            "User name",
            "Contributor",
            "Editor",
            "Member",
            "Reader",
            "Reviewer",
            "Site Administrator",
            "Manager",
        ]
        for index, header in enumerate(headers):
            assert header.get_text(strip=True) == expected_headers[index]
