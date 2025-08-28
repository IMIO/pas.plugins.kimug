"""Installer for the pas.plugins.kimug package."""

from pathlib import Path
from setuptools import find_packages
from setuptools import setup


long_description = f"""
{Path("README.md").read_text()}\n
{Path("CONTRIBUTORS.md").read_text()}\n
{Path("CHANGES.md").read_text()}\n
"""


setup(
    name="pas.plugins.kimug",
    version="1.1.4",
    description="A PAS plugin to set roles to imio keycloak users",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Plone",
        "Framework :: Plone :: Addon",
        "Framework :: Plone :: 6.0",
        "Framework :: Plone :: 6.1",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
    ],
    keywords="Python Plone CMS",
    author="iMio",
    author_email="devops@imio.be",
    url="https://github.com/imio/pas.plugins.kimug",
    project_urls={
        "PyPI": "https://pypi.org/project/pas.plugins.kimug",
        "Source": "https://github.com/imio/pas.plugins.kimug",
        "Tracker": "https://github.com/imio/pas.plugins.kimug/issues",
    },
    license="GPL version 2",
    packages=find_packages("src", exclude=["ez_setup"]),
    namespace_packages=["pas", "pas.plugins"],
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.10",
    install_requires=[
        "setuptools",
        "Products.CMFPlone",
        "plone.api",
        "pas.plugins.oidc>=2.0.0b4",
        "python-keycloak",
    ],
    extras_require={
        "test": [
            "ipdb",
            "zest.releaser[recommended]",
            "zestreleaser.towncrier",
            "plone.app.testing",
            "plone.classicui",
            "plone.restapi[test]",
            "pytest",
            "pytest-cov",
            "pytest-plone>=0.5.0",
            "pytest-docker",
        ],
    },
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    [console_scripts]
    update_locale = pas.plugins.kimug.locales.update:update_locale
    """,
)
