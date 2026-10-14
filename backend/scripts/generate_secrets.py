"""Prints fresh production secrets in the exact form the Railway variables take.

Run from the backend folder:

    python scripts/generate_secrets.py

It prints DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEYS, JWT_PRIVATE_KEY and JWT_PUBLIC_KEY, one per
line as NAME=value. Paste each value into Railway (Variables, New Variable) and keep the output
out of the repository and out of chat. Nothing is written to disk: the keys exist only in the
terminal, so copy them before closing it. Run it again for a new set; a new JWT pair signs
everyone out, and new FIELD_ENCRYPTION_KEYS cannot read data encrypted with the old ones (to
rotate, put the new key first and keep the old one after a comma).

The JWT keys are Ed25519 PEM text on one line, with a literal backslash and n between the lines.
The settings turn those back into line breaks.
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet  # noqa: E402

from config.settings.keys import ephemeral_jwt_keys  # noqa: E402


def one_line(pem: str) -> str:
    return pem.strip().replace("\n", "\\n")


def main() -> None:
    private, public = ephemeral_jwt_keys()
    print(f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}")  # noqa: T201
    print(f"FIELD_ENCRYPTION_KEYS={Fernet.generate_key().decode()}")  # noqa: T201
    print(f"JWT_PRIVATE_KEY={one_line(private)}")  # noqa: T201
    print(f"JWT_PUBLIC_KEY={one_line(public)}")  # noqa: T201


if __name__ == "__main__":
    main()
