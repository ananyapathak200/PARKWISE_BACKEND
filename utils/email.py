"""
utils/email.py — sends password reset emails using Gmail SMTP.
Settings come from config.py (.env); the password is never logged.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from urllib.parse import urlencode

from config import SMTP_EMAIL, SMTP_APP_PASSWORD, FRONTEND_RESET_URL

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

log = logging.getLogger("parkwise.email")


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """
    Send a password reset email through Gmail SMTP. Runs as a background
    task, so failures are logged (without the address or token) instead of
    being shown to the visitor.
    """
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        log.error("Password reset email not sent: SMTP_EMAIL / SMTP_APP_PASSWORD missing in .env")
        return

    separator = "&" if "?" in FRONTEND_RESET_URL else "?"
    reset_link = f"{FRONTEND_RESET_URL}{separator}{urlencode({'token': reset_token})}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your ParkWise password"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    text_body = f"""Hi,

Someone requested a password reset for your ParkWise account.

Use the link below to reset your password:
{reset_link}

This link expires in 30 minutes.

If you didn't request this, you can safely ignore this email.

— ParkWise
"""

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1B1D1F;">
        <div style="max-width: 480px; margin: 0 auto; padding: 20px;">
          <h2>Reset your ParkWise password</h2>
          <p>Someone requested a password reset for your account.</p>
          <p>
            <a href="{escape(reset_link, quote=True)}"
               style="display:inline-block; background:#FFB020;
                      color:#1B1D1F; padding:12px 24px;
                      border-radius:8px; text-decoration:none;
                      font-weight:bold;">
              Reset Password
            </a>
          </p>
          <p>This link expires in 30 minutes.</p>
          <p>If you didn't request this, you can safely ignore this email.</p>
          <p>— ParkWise</p>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.send_message(msg)
        log.info("Password reset email sent")
    except (smtplib.SMTPException, OSError) as exc:
        log.error("Password reset email failed: %s", type(exc).__name__)
