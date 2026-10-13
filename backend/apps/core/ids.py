import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Time ordered UUID (RFC 9562 version 7).

    Python 3.12 has no built in generator. Time ordering keeps primary key
    indexes append mostly, which matters for the large tables.
    """
    millis = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 68) & 0xFFF
    rand_b = rand & ((1 << 62) - 1)
    value = (millis << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
