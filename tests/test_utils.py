"""Testes para core.utils (timestamps)."""
import re
from datetime import datetime, timezone

from core.utils import format_timestamp, get_current_timestamp, get_timestamp_iso


def test_current_timestamp_is_timezone_aware() -> None:
    ts = get_current_timestamp()

    assert ts.tzinfo is not None


def test_format_timestamp_pt_br() -> None:
    dt = datetime(2026, 3, 20, 14, 30, 45)

    assert format_timestamp(dt) == "20/03/2026 14:30:45"


def test_iso_timestamp_is_parseable() -> None:
    iso = get_timestamp_iso()

    parsed = datetime.fromisoformat(iso)
    assert parsed.tzinfo is not None


def test_iso_timestamp_with_explicit_datetime() -> None:
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    assert get_timestamp_iso(dt) == "2026-01-01T12:00:00+00:00"


def test_format_matches_expected_pattern() -> None:
    formatted = format_timestamp(get_current_timestamp())

    assert re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", formatted)
