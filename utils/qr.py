"""
utils/qr.py — generates the unique token embedded in each booking's QR
code. We don't render an actual QR image server-side in the MVP; the
frontend can render this token as a QR code with any JS QR library, or
you can add image generation here later with the `qrcode` package.
"""

import secrets
import string


def generate_qr_token() -> str:
    alphabet = string.ascii_uppercase + string.digits
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"PW-{part1}-{part2}"
