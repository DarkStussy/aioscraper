import os
import sys

sys.path.insert(0, os.path.abspath("."))

# Project information
project = "aioscraper"
copyright = "2025, darkstussy"
author = "darkstussy"
master_doc = "index"

# General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_design",
]
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}
autodoc_type_aliases = {}
autodoc_typehints = "description"

templates_path = ["_templates"]

exclude_patterns = []

# HTML conf
html_theme = "furo"
html_favicon = "static/aioscraper.png"
html_theme_options = {
    "light_logo": "aioscraper.png",
    "dark_logo": "aioscraper.png",
    "sidebar_hide_name": True,
}

html_static_path = ["static"]
