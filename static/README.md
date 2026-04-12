# Project `static/` directory

This folder is included in **`STATICFILES_DIRS`** (see `analytics_project/settings/base.py`). Files here are collected into **`STATIC_ROOT`** when you run **`collectstatic`**, alongside assets from each app’s **`static/`** tree (for example **`dashboard/static/`**).

## Contents

- **`icons/`** — shared SVG assets (for example OS and browser icons) referenced from templates via **`{% static 'icons/...' %}`**.

App-specific CSS, JavaScript, and images usually live under **`dashboard/static/`**, **`tools/static/`**, etc., not here. Use this directory when an asset is shared across apps or does not belong to a single app package.
