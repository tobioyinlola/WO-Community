from apps.core.ids import uuid7


def test_uuid7_is_version_7_and_variant_rfc():
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_sorts_by_creation_time():
    values = []
    import time

    for _ in range(5):
        values.append(uuid7())
        time.sleep(0.002)
    assert values == sorted(values)
    assert len(set(values)) == 5
