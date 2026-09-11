"""Gmail API transport for the main OnboardHub portal.

This module sends mail through Gmail's REST API over HTTPS instead of SMTP.
It uses the narrow gmail.send OAuth scope and a stored OAuth refresh token so
Render Free can send mail without opening SMTP ports 25/465/587.
"""
import base64
import json
from email.message import EmailMessage
from urllib.parse import urlencode

import requests

from .models import AppSetting

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


def _clean(value):
    return (value or "").replace("\ufeff", "").strip().strip('"\'')


def client_id():
    return _clean(AppSetting.get("gmail_client_id"))


def client_secret():
    return _clean(AppSetting.get("gmail_client_secret"))


def refresh_token():
    return _clean(AppSetting.get("gmail_refresh_token"))


def account_email():
    return _clean(AppSetting.get("gmail_account_email"))


def sender_name():
    return _clean(AppSetting.get("gmail_sender_name") or AppSetting.get("smtp_from_name") or "OnboardHub")


def configured():
    return bool(client_id() and client_secret() and refresh_token())


def authorization_url(redirect_uri, state):
    if not client_id():
        raise RuntimeError("Gmail OAuth Client ID is not configured.")
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code, redirect_uri):
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if not response.ok:
        try:
            detail = response.json().get("error_description") or response.json().get("error")
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(f"Google OAuth token exchange failed: {detail or response.status_code}")
    data = response.json()
    token = data.get("refresh_token")
    if not token:
        raise RuntimeError("Google did not return a refresh token. Re-authorize with consent enabled.")
    return token


def _access_token():
    if not configured():
        raise RuntimeError("Gmail API is not configured. Add Client ID, Client Secret and authorize the Gmail account.")
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id(),
            "client_secret": client_secret(),
            "refresh_token": refresh_token(),
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if not response.ok:
        try:
            payload = response.json()
            detail = payload.get("error_description") or payload.get("error")
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(f"Gmail OAuth refresh failed: {detail or response.status_code}")
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Google OAuth refresh response did not contain an access token.")
    return token


def fetch_account_email():
    token = _access_token()
    response = requests.get(
        PROFILE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(_api_error("Gmail profile request failed", response))
    email = _clean(response.json().get("emailAddress"))
    if not email:
        raise RuntimeError("Gmail profile did not return an account email address.")
    return email


def _api_error(prefix, response):
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload.get("error"), dict) else payload.get("error_description")
        return f"{prefix}: {message or response.status_code}"
    except ValueError:
        return f"{prefix}: HTTP {response.status_code}"


def send_email(to, subject, body, html=None):
    """Send an email through Gmail API. Returns (ok, error, message_id)."""
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [str(value).strip() for value in recipients if str(value).strip()]
    if not recipients:
        return False, "No email recipients were supplied.", None
    if not configured():
        return False, "Gmail API is not configured.", None

    try:
        sender = account_email()
        if not sender:
            sender = fetch_account_email()
            AppSetting.set("gmail_account_email", sender)

        message = EmailMessage()
        message["To"] = ", ".join(recipients)
        message["From"] = f"{sender_name()} <{sender}>"
        message["Subject"] = subject or ""
        message.set_content(body or "")
        if html:
            message.add_alternative(html, subtype="html")

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        token = _access_token()
        response = requests.post(
            SEND_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=25,
        )
        if not response.ok:
            return False, _api_error("Gmail API send failed", response), None

        data = response.json()
        return True, None, data.get("id")
    except requests.RequestException as exc:
        return False, f"Gmail API HTTPS request failed: {type(exc).__name__}: {exc}", None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None
