"""
Test helpers for HTMX-based view testing.

Provides base classes and utilities for testing HTMX views that return
HTML fragments instead of full pages.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User

try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFULSOUP = True
except ImportError:
    HAS_BEAUTIFULSOUP = False


class HTMXViewTestCase(TestCase):
    """
    Base class for testing HTMX views.

    Provides:
    - Auto-login test user
    - HTMX request helpers (get_with_htmx, post_with_htmx)
    - HTML parsing utilities
    - Assertion helpers for common patterns
    """

    # Override these in subclasses if needed
    test_username = 'testuser'
    test_password = 'testpass123'
    test_email = 'test@example.com'

    @classmethod
    def setUpTestData(cls):
        """Create test user once for all tests in the class."""
        cls.user = User.objects.create_user(
            username=cls.test_username,
            password=cls.test_password,
            email=cls.test_email,
        )

    def setUp(self):
        """Log in the test user before each test."""
        super().setUp()
        self.client = Client()
        self.client.login(username=self.test_username, password=self.test_password)

    def get_with_htmx(self, url, **kwargs):
        """
        Make a GET request with HTMX headers.

        Args:
            url: The URL to request
            **kwargs: Additional arguments passed to client.get()

        Returns:
            HttpResponse
        """
        headers = kwargs.pop('headers', {})
        headers['HX-Request'] = 'true'
        return self.client.get(url, headers=headers, **kwargs)

    def post_with_htmx(self, url, data=None, **kwargs):
        """
        Make a POST request with HTMX headers.

        Args:
            url: The URL to request
            data: Form data to post
            **kwargs: Additional arguments passed to client.post()

        Returns:
            HttpResponse
        """
        headers = kwargs.pop('headers', {})
        headers['HX-Request'] = 'true'
        return self.client.post(url, data=data or {}, headers=headers, **kwargs)

    def parse_html(self, response):
        """
        Parse response content as HTML using BeautifulSoup.

        Args:
            response: HttpResponse or string content

        Returns:
            BeautifulSoup object

        Raises:
            RuntimeError if BeautifulSoup is not installed
        """
        if not HAS_BEAUTIFULSOUP:
            raise RuntimeError(
                "BeautifulSoup is required for HTML parsing. "
                "Install it with: pip install beautifulsoup4"
            )

        if hasattr(response, 'content'):
            content = response.content.decode('utf-8')
        else:
            content = response

        return BeautifulSoup(content, 'html.parser')

    def assert_contains_element(self, response, selector, count=None, msg=None):
        """
        Assert that the response contains element(s) matching the CSS selector.

        Args:
            response: HttpResponse
            selector: CSS selector string
            count: If provided, assert exactly this many elements match
            msg: Optional failure message

        Raises:
            AssertionError if selector doesn't match or count is wrong
        """
        soup = self.parse_html(response)
        elements = soup.select(selector)

        if count is not None:
            self.assertEqual(
                len(elements),
                count,
                msg or f"Expected {count} elements matching '{selector}', found {len(elements)}"
            )
        else:
            self.assertGreater(
                len(elements),
                0,
                msg or f"Expected at least one element matching '{selector}', found none"
            )

        return elements

    def assert_not_contains_element(self, response, selector, msg=None):
        """
        Assert that the response does NOT contain any elements matching the selector.

        Args:
            response: HttpResponse
            selector: CSS selector string
            msg: Optional failure message
        """
        soup = self.parse_html(response)
        elements = soup.select(selector)

        self.assertEqual(
            len(elements),
            0,
            msg or f"Expected no elements matching '{selector}', found {len(elements)}"
        )

    def assert_table_row_count(self, response, selector='table tbody tr', expected_count=None, min_count=None):
        """
        Assert the number of rows in a table.

        Args:
            response: HttpResponse
            selector: CSS selector for table rows (default: 'table tbody tr')
            expected_count: Assert exactly this many rows
            min_count: Assert at least this many rows
        """
        soup = self.parse_html(response)
        rows = soup.select(selector)

        if expected_count is not None:
            self.assertEqual(
                len(rows),
                expected_count,
                f"Expected {expected_count} table rows, found {len(rows)}"
            )
        elif min_count is not None:
            self.assertGreaterEqual(
                len(rows),
                min_count,
                f"Expected at least {min_count} table rows, found {len(rows)}"
            )

        return rows

    def get_element_text(self, response, selector):
        """
        Get the text content of the first element matching the selector.

        Args:
            response: HttpResponse
            selector: CSS selector string

        Returns:
            String text content, or None if not found
        """
        soup = self.parse_html(response)
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else None

    def get_all_element_texts(self, response, selector):
        """
        Get the text content of all elements matching the selector.

        Args:
            response: HttpResponse
            selector: CSS selector string

        Returns:
            List of string text contents
        """
        soup = self.parse_html(response)
        elements = soup.select(selector)
        return [el.get_text(strip=True) for el in elements]

    def assert_hx_trigger(self, response, expected_trigger):
        """
        Assert that the response has the expected HX-Trigger header.

        Args:
            response: HttpResponse
            expected_trigger: Expected trigger value
        """
        trigger = response.get('HX-Trigger')
        self.assertEqual(
            trigger,
            expected_trigger,
            f"Expected HX-Trigger '{expected_trigger}', got '{trigger}'"
        )

    def assert_hx_redirect(self, response, expected_url):
        """
        Assert that the response has the expected HX-Redirect header.

        Args:
            response: HttpResponse
            expected_url: Expected redirect URL
        """
        redirect = response.get('HX-Redirect')
        self.assertEqual(
            redirect,
            expected_url,
            f"Expected HX-Redirect to '{expected_url}', got '{redirect}'"
        )

    def assert_form_errors(self, response, field_name=None):
        """
        Assert that the response contains form error messages.

        Args:
            response: HttpResponse
            field_name: If provided, assert error exists for this specific field

        Returns:
            List of error elements found
        """
        if field_name:
            selector = f'.invalid-feedback, .errorlist, [id*="{field_name}"][class*="error"]'
        else:
            selector = '.invalid-feedback, .errorlist, .alert-danger'

        return self.assert_contains_element(response, selector)


class AuthenticatedAPITestCase(HTMXViewTestCase):
    """
    Alias for HTMXViewTestCase for compatibility.

    Use this when testing API-like HTMX endpoints that return
    structured data in HTML format.
    """
    pass


def create_test_user(username='testuser', password='testpass123', email='test@example.com'):
    """
    Create a test user for use in tests.

    Args:
        username: Username for the test user
        password: Password for the test user
        email: Email for the test user

    Returns:
        User instance
    """
    return User.objects.create_user(
        username=username,
        password=password,
        email=email,
    )
