"""Errors shared by several accounts modules."""

from rest_framework import exceptions


class InvalidToken(exceptions.ValidationError):
    """An emailed link (verification, reset, invitation) is unknown, used or expired."""

    default_code = "invalid_token"

    def __init__(self) -> None:
        super().__init__({"token": ["This link is invalid or has expired."]}, code="invalid_token")
