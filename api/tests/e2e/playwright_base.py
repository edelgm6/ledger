"""Shared Playwright base with htmx- and Alpine-aware waiting.

These tests were flaky at roughly a 3-in-8 failure rate, in two distinct
shapes: a ~30s Playwright timeout, and a fast (~2s) assertion failure against
stale DOM. Both came from waiting on the wrong thing.

``wait_for_load_state("networkidle")`` was used as a stand-in for "htmx has
finished updating the page". It is not one. It reports that the *network* went
quiet for 500ms, which says nothing about whether htmx has swapped its
response into the document -- the swap happens after the response arrives, so
an assertion could run against the old DOM and fail fast. And because it waits
on network silence rather than on a condition the page actually reaches, it
times out under load even when the page is fine.

Fixed ``wait_for_timeout(150)`` sleeps had the same defect for Alpine: they
guess at how long a reactive re-render takes, and lose that guess on a loaded
machine.

This base replaces both with waits on the condition itself:

``wait_for_htmx``
    Blocks until no htmx request is in flight *and* every response has been
    swapped and settled. Backed by a counter installed from htmx's own
    lifecycle events.
``wait_for_text`` / ``wait_for_no_text``
    Blocks until a selector's text does (or no longer does) contain a string --
    which is what the Alpine sleeps were approximating.
"""

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

from django.test import LiveServerTestCase, tag
from playwright.sync_api import sync_playwright

# Counts htmx requests that have started but not yet settled. Installed on
# every navigation, on document.body so it survives hx-boost (which swaps
# #container, not body). Decrements on every terminal outcome htmx can reach,
# not just success, so a failed request cannot wedge the counter above zero.
HTMX_TRACKER = """
document.addEventListener('DOMContentLoaded', () => {
    if (window.__htmxPendingInstalled) return;
    window.__htmxPendingInstalled = true;
    window.__htmxPending = 0;
    const done = () => {
        window.__htmxPending = Math.max(0, window.__htmxPending - 1);
    };
    document.body.addEventListener('htmx:beforeRequest', () => {
        window.__htmxPending += 1;
    });
    document.body.addEventListener('htmx:afterSettle', done);
    document.body.addEventListener('htmx:responseError', done);
    document.body.addEventListener('htmx:sendError', done);
    document.body.addEventListener('htmx:timeout', done);
    document.body.addEventListener('htmx:swapError', done);
});
"""


@tag("e2e")
class PlaywrightTestCase(LiveServerTestCase):
    """LiveServerTestCase with a browser and deterministic waits."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.context = self.browser.new_context()
        self.context.add_init_script(HTMX_TRACKER)
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()
        super().tearDown()

    # --- waits ------------------------------------------------------------

    def goto(self, path):
        """Navigates and waits until htmx and Alpine are both usable."""
        self.page.goto(self.live_server_url + path)
        self.page.wait_for_function("() => typeof htmx !== 'undefined'")
        self.page.wait_for_function("() => typeof Alpine !== 'undefined'")
        # Fail loudly if the tracker did not install. Without this check a
        # missing tracker would make wait_for_htmx return instantly, silently
        # restoring the race it exists to prevent.
        self.page.wait_for_function("() => window.__htmxPendingInstalled === true")
        self.wait_for_htmx()

    def wait_for_htmx(self):
        """Blocks until every in-flight htmx request has swapped and settled.

        This is the replacement for networkidle: it waits on the page reaching
        a known state rather than on the network happening to go quiet.
        """
        # Requires the counter to exist: treating "undefined" as settled would
        # turn a failed tracker install into a silently passing no-op wait.
        self.page.wait_for_function("() => window.__htmxPending === 0")

    def wait_for_text(self, selector, text):
        """Blocks until `selector`'s text contains `text`."""
        self.page.wait_for_function(
            """([sel, needle]) => {
                const el = document.querySelector(sel);
                return !!el && el.innerText.includes(needle);
            }""",
            arg=[selector, text],
        )

    def wait_for_no_text(self, selector, text):
        """Blocks until `selector`'s text no longer contains `text`."""
        self.page.wait_for_function(
            """([sel, needle]) => {
                const el = document.querySelector(sel);
                return !!el && !el.innerText.includes(needle);
            }""",
            arg=[selector, text],
        )

    def click_in_scroll_container(self, selector):
        """Clicks an element inside a scrollable table, centering it first.

        `.table th` is `position: sticky; z-index: 1` and the transactions
        table lives in a 200px-max scroll container, so Playwright's default
        scrollIntoView can land the target row directly beneath its own sticky
        header -- which then intercepts the click. Playwright retries for 30s
        and reports "<table class=\"table\"> intercepts pointer events".
        Centering the row in its container puts it clear of the header.
        """
        locator = self.page.locator(selector)
        locator.scroll_into_view_if_needed()
        locator.evaluate("el => el.scrollIntoView({block: 'center'})")
        locator.click()

    def wait_for_visible_text(self, selector, expected):
        """Blocks until the *visible* elements matching `selector` have exactly
        `expected` as their .td-name text, in order.

        Waits on the same predicate the assertion uses. Waiting on a nearby
        signal instead -- the live count, say -- is not equivalent: the count
        and the row visibility are separate Alpine effects, and the count
        settles first, so a test can observe an updated count beside rows that
        have not been hidden yet.
        """
        self.page.wait_for_function(
            """([sel, want]) => {
                const visible = Array.from(document.querySelectorAll(sel))
                    .filter(e => e.offsetParent !== null)
                    .map(e => e.querySelector('.td-name').innerText.trim());
                return visible.length === want.length
                    && visible.every((v, i) => v === want[i]);
            }""",
            arg=[selector, list(expected)],
        )

    def visible_text(self, selector):
        """The .td-name text of the currently visible elements."""
        return self.page.eval_on_selector_all(
            selector,
            """els => els.filter(e => e.offsetParent !== null)
                        .map(e => e.querySelector('.td-name').innerText.trim())""",
        )

    def wait_for_option_values(self, selector, *, includes=(), excludes=()):
        """Blocks until a <select>'s option values satisfy the given sets.

        Replaces sleeping after select_option and hoping the dependent select
        has been rebuilt.
        """
        self.page.wait_for_function(
            """([sel, inc, exc]) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                const values = Array.from(el.options).map(o => o.value);
                return inc.every(v => values.includes(v))
                    && exc.every(v => !values.includes(v));
            }""",
            arg=[selector, list(includes), list(excludes)],
        )
