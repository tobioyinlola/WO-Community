"""Test helpers for signed provider webhooks."""

import base64
import hashlib
import hmac
import time


def sign(body: bytes, secret: str, delivery_id="msg_abc", timestamp=None, versions=("v1",)):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{delivery_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    return {
        "svix-id": delivery_id,
        "svix-timestamp": timestamp,
        "svix-signature": " ".join(f"{v},{signature}" for v in versions),
    }
