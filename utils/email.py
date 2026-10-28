
"""
utils/email.py — sends password reset emails using Gmail SMTP.
"""

import os
import smtplib
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# Load .env from the parkwise-backend root directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)


# Email configuration
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "").strip()
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "").strip()

FRONTEND_RESET_URL = os.getenv(
    "FRONTEND_RESET_URL",
    "http://127.0.0.1:5501/parkwise-frontend/reset-password.html"
).strip().rstrip("?&")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """
    Send a password reset email through Gmail SMTP.
    Raises an exception if configuration or sending fails.
    """

    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        raise RuntimeError(
            "SMTP configuration missing. Check SMTP_EMAIL and "
            "SMTP_APP_PASSWORD in the backend .env file."
        )

    # Build the reset link safely
    separator = "&" if "?" in FRONTEND_RESET_URL else "?"
    reset_link = (
        f"{FRONTEND_RESET_URL}{separator}"
        f"{urlencode({'token': reset_token})}"
    )

    # Create email
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
            <a href="{reset_link}"
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

    # Connect, authenticate, and send
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.send_message(msg)

        print(f"Password reset email sent successfully to {to_email}")

    except (smtplib.SMTPException, OSError) as exc:
        print(f"Password reset email failed: {type(exc).__name__}: {exc}")
        raise
