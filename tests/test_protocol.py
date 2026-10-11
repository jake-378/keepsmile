import pytest

from keepsmile import protocol
from keepsmile.protocol import Protocol


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("KS03-1A2B3C", Protocol.LEGACY),
        ("KS04-0001", Protocol.LEGACY),
        ("KS03~1A2B3C", Protocol.MODERN),
        ("KS14~0001", Protocol.MODERN),
        (None, Protocol.MODERN),
    ],
)
def test_protocol_for_name(name, expected):
    assert protocol.protocol_for_name(name) is expected


def test_legacy_frames():
    assert protocol.power(Protocol.LEGACY, True).hex(" ") == "7e 04 04 f0 01 01 ff 00 ef"
    assert protocol.power(Protocol.LEGACY, False).hex(" ") == "7e 04 04 10 01 00 ff 00 ef"
    assert protocol.color(Protocol.LEGACY, 0x12, 0x34, 0x56).hex(" ") == "7e 07 05 03 12 34 56 00 ef"
    assert protocol.brightness(Protocol.LEGACY, 50).hex(" ") == "7e 04 01 32 ff ff ff 00 ef"


def test_modern_frames():
    assert protocol.power(Protocol.MODERN, True).hex(" ") == "5b f0 00 b5"
    assert protocol.power(Protocol.MODERN, False).hex(" ") == "5b 0f 00 b5"
    assert protocol.color(Protocol.MODERN, 0x12, 0x34, 0x56, 80).hex(" ") == "5a 00 01 12 34 56 00 50 00 a5"
    assert protocol.brightness(Protocol.MODERN, 10, (255, 0, 0)).hex(" ") == "5a 00 01 ff 00 00 00 0a 00 a5"


@pytest.mark.parametrize("bad", [-1, 101])
def test_brightness_range(bad):
    with pytest.raises(ValueError):
        protocol.brightness(Protocol.LEGACY, bad)


def test_handshake_frames():
    from datetime import datetime

    assert protocol.QUERY_STATE.hex(" ") == "5f 01 00 f5"
    # 2026-10-11 is a Sunday, which NSCalendar numbers as 1.
    assert protocol.time_sync(datetime(2026, 10, 11, 20, 5, 9)).hex(" ") == "7e 07 83 14 05 09 01 ff ef"


def test_parse_state_report_from_real_strip():
    state = protocol.parse_state(bytes.fromhex("5f 06 01 f0 ff 00 00 00 29 3f 00 f5"))
    assert state == protocol.LightState(on=True, rgb=(255, 0, 0), brightness=41)
    assert protocol.parse_state(bytes.fromhex("5f 06 01 0f 00 ff 00 00 64 3f 00 f5")).on is False
    assert protocol.parse_state(bytes.fromhex("7e 04 04 f0 01 01 ff 00 ef")) is None


def test_color_range():
    with pytest.raises(ValueError):
        protocol.color(Protocol.LEGACY, 256, 0, 0)
