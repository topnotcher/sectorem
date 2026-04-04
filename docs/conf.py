"""Sphinx configuration for sectorem documentation."""

project = "sectorem"
copyright = "2026, Greg Bowser"
author = "Greg Bowser"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_class_signature = "separated"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable", None),
}

nitpick_ignore = [
    ("py:class", "aiohttp.client.ClientSession"),
    ("py:class", "ServerFactory"),
    ("py:data", "AuthCallback"),
]
