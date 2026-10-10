"""No Django template syntax may survive into rendered HTML.

Django's `{# ... #}` comment is **single-line only**. A multi-line one is not a
comment at all -- it renders verbatim into the page. That happened twice in the
Settings and nav templates, shipping explanatory prose into the markup of every
page, so this guards the whole shell rather than the two sites that regressed.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

PAGES = [
    ("index", []),
    ("journal-entries", []),
    ("transactions", []),
    ("taxes", []),
    ("reconciliation", []),
    ("amortization", []),
    ("recharacterize", []),
    ("settings", []),
    ("trend", []),
    ("statements", ["income"]),
    ("statements", ["balance"]),
    ("statements", ["cash"]),
]


class NoTemplateSyntaxLeaksTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="leaks", password="p")
        self.client = Client()
        self.client.force_login(self.user)

    def test_no_unrendered_template_syntax_in_any_page(self):
        for url_name, args in PAGES:
            with self.subTest(url_name=url_name, args=args):
                html = self.client.get(
                    reverse(url_name, args=args), follow=True
                ).content.decode()
                # An unclosed/multi-line {# #} leaves its opener in the output.
                self.assertNotIn(
                    "{#", html, f"{url_name}: a template comment leaked"
                )
                # Unrendered tags would mean a syntax or context problem.
                for marker in ("{% comment %}", "{% endcomment %}", "{% if ", "{% for "):
                    self.assertNotIn(
                        marker, html, f"{url_name}: {marker!r} was not rendered"
                    )
