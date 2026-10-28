"""
utils/payments.py — all Razorpay interaction lives here, in one place,
so the security-critical signature verification is easy to review.

SECURITY NOTES (read before touching this file):
- RAZORPAY_KEY_SECRET must only ever be read from the environment here.
  It must never be sent to the frontend, logged, or hardcoded.
- verify_payment_signature() is the ONLY thing that should ever mark a
  booking as paid. Never trust a "payment succeeded" message that comes
  from the frontend alone — Razorpay's client-side success callback can
  be spoofed by anyone with browser dev tools. The signature is an
  HMAC-SHA256 that only someone holding the real key_secret could have
  produced, which is why this check is what actually matters.
"""

import os
import hmac
import hashlib
import razorpay

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError(
        "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set. "
        "Copy .env.example to .env and fill in your Razorpay test keys."
    )

_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def create_order(amount_rupees: float, receipt: str) -> dict:
    """
    Creates a Razorpay Order. Amount must be sent to Razorpay in paise
    (1 rupee = 100 paise) — this is a Razorpay API requirement, not a
    ParkWise convention, so don't "simplify" this away.
    """
    amount_paise = int(round(amount_rupees * 100))
    order = _client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,  # auto-capture once payment succeeds
    })
    return order


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Recomputes the expected signature server-side using the secret key,
    and compares it against what the frontend sent back from Razorpay.
    Returns False on any mismatch or malformed input — never raises,
    so callers can't accidentally treat an exception as "verified".
    """
    try:
        _client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False