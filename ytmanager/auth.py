"""OAuth handling: run the consent flow once, then reuse the cached token."""

import os
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CLIENT_SECRET = Path(os.environ.get("YTM_CLIENT_SECRET", "client_secret.json"))
TOKEN_FILE = Path(os.environ.get("YTM_TOKEN", "token.json"))


def get_credentials(console=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CLIENT_SECRET.exists():
            raise SystemExit(
                f"Missing {CLIENT_SECRET}. Download an OAuth 'Desktop app' client from "
                "Google Cloud Console and save it there (or set YTM_CLIENT_SECRET)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        if console:
            creds = flow.run_local_server(port=0, open_browser=False)
        else:
            creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def youtube(creds=None):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds or get_credentials(), cache_discovery=False)


def analytics(creds=None):
    from googleapiclient.discovery import build

    return build("youtubeAnalytics", "v2", credentials=creds or get_credentials(), cache_discovery=False)
