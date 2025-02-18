from AccessControl.SecurityManagement import newSecurityManager
from pas.plugins.kimug.interfaces import IBrowserLayer
from Products.CMFPlone.factory import _DEFAULT_PROFILE
from Products.CMFPlone.factory import addPloneSite
from Products.GenericSetup.tool import SetupTool
from Testing.makerequest import makerequest
from zope.interface import directlyProvidedBy
from zope.interface import directlyProvides

import os
import transaction


truthy = frozenset(("t", "true", "y", "yes", "on", "1"))


def asbool(s):
    """Return the boolean value ``True`` if the case-lowered value of string
    input ``s`` is a :term:`truthy string`. If ``s`` is already one of the
    boolean values ``True`` or ``False``, return it."""
    if s is None:
        return False
    if isinstance(s, bool):
        return s
    s = str(s).strip()
    return s.lower() in truthy


DELETE_EXISTING = asbool(os.getenv("DELETE_EXISTING"))

app = makerequest(globals()["app"])

request = app.REQUEST

ifaces = [IBrowserLayer] + list(directlyProvidedBy(request))

directlyProvides(request, *ifaces)

admin = app.acl_users.getUserById("admin")
admin = admin.__of__(app.acl_users)
newSecurityManager(None, admin)

site_id = "Plone"
payload = {
    "title": "pas.plugins.kimug",
    "profile_id": _DEFAULT_PROFILE,
    "distribution_name": "classic",
    "setup_content": False,
    "default_language": "en",
    "portal_timezone": "UTC",
}

if site_id in app.objectIds() and DELETE_EXISTING:
    app.manage_delObjects([site_id])
    transaction.commit()
    app._p_jar.sync()

if site_id not in app.objectIds():
    site = addPloneSite(app, site_id, **payload)
    transaction.commit()

    portal_setup: SetupTool = site.portal_setup
    portal_setup.runAllImportStepsFromProfile("profile-pas.plugins.kimug:default")

    acl_user = site.acl_users
    oidc = acl_user.oidc
    oidc.client_id = "plone"
    oidc.client_secret = "12345678910"
    oidc.issuer = "http://127.0.0.1:8180/realms/plone/"
    oidc.redirect_uris = ("http://localhost:8080/Plone/acl_users/oidc/callback",)
    oidc.scope = ("openid", "profile", "email")

    from plone import api

    api.portal.set_registry_record("plone.external_login_url", "acl_users/oidc/login")
    api.portal.set_registry_record("plone.external_logout_url", "acl_users/oidc/logout")

    transaction.commit()
