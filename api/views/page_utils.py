"""Shared view utilities for full-page rendering.

Navbar-destination views build their content as an HTML fragment (the same
fragment HTMX swaps into ``#container``) and wrap it in the full ``base.html``
shell via :func:`render_full_page`. This means a direct browser load of any
navbar URL (open-in-new-tab, refresh, bookmark) returns a complete, styled
page. In-app navigation stays fast because the navbar uses ``hx-boost`` with
``hx-select="#container"``, which extracts just ``#container`` out of this
full response.
"""

from django.http import HttpResponse
from django.shortcuts import render


def render_full_page(request, content_html: str) -> HttpResponse:
    """Wrap a pre-rendered content fragment in the base.html shell."""
    return render(request, "api/shell.html", {"content": content_html})
