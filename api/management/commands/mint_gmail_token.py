"""
One-time helper: run the OAuth installed-app flow to mint a Gmail refresh
token. Run locally once, then set GMAIL_REFRESH_TOKEN (in local_settings.py for
dev, or as a Heroku config var for production).

Requires GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET to be set first.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the OAuth flow to mint a Gmail refresh token (read-only scope)."

    def handle(self, *args, **options):
        from google_auth_oauthlib.flow import InstalledAppFlow

        from api.services.gmail_services import GMAIL_SCOPES, GMAIL_TOKEN_URI

        client_id = settings.GMAIL_CLIENT_ID
        client_secret = settings.GMAIL_CLIENT_SECRET
        if not (client_id and client_secret):
            raise CommandError(
                "Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET before running."
            )

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": GMAIL_TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes=GMAIL_SCOPES)
        credentials = flow.run_local_server(
            port=0, access_type="offline", prompt="consent"
        )

        if not credentials.refresh_token:
            raise CommandError(
                "No refresh token returned. Revoke prior access and retry with "
                "prompt=consent."
            )

        # Persist to a file as well as stdout, so backgrounded/interactive runs
        # don't lose the token to stdout-capture quirks.
        token_path = Path(settings.BASE_DIR) / ".gmail_refresh_token"
        token_path.write_text(credentials.refresh_token)

        self.stdout.write(self.style.SUCCESS("GMAIL_REFRESH_TOKEN:"))
        self.stdout.write(credentials.refresh_token)
        self.stdout.write(self.style.SUCCESS(f"\nAlso written to: {token_path}"))
