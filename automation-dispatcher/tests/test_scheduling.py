from __future__ import annotations

from datetime import datetime, timezone

import pytest

from automation_dispatcher.definitions import DefinitionError
from automation_dispatcher.scheduling import (
    collection_due_occurrences,
    collection_occurrences_between,
    normalize_collection_schedule,
)


UTC = timezone.utc


def config(expression: str = "0 6 * * *", **overrides: object) -> dict:
    result = {
        "timezone": "America/Chicago",
        "schedule": {"version": 2, "kind": "cron", "expression": expression},
        "enabled": True,
        "max_lateness_seconds": 7200,
        "catch_up": {"policy": "bounded", "max_lookback_seconds": 86400},
    }
    result.update(overrides)
    return result


def test_presets_normalize_without_defining_dispatcher_identity() -> None:
    assert normalize_collection_schedule({"preset": "daily", "time": "06:00"}) == {
        "version": 2,
        "kind": "cron",
        "expression": "0 6 * * *",
    }
    assert normalize_collection_schedule(
        {"preset": "weekly", "time": "16:00", "weekdays": ["fri", "monday", "fri"]}
    ) == {"version": 2, "kind": "cron", "expression": "0 16 * * 1,5"}


@pytest.mark.parametrize(
    "expression",
    [
        "0 0 1 * 1",  # DOM and DOW simultaneously constrained
        "@daily",
        "0 0 * *",  # only four fields
        "0 0 * * * *",  # seconds/extensions are unsupported
        "60 0 * * *",
        "0 24 * * *",
        "0 0 L * *",
        "0 0 ? * *",
        "0 0 * JAN *",
        "0 0 * * MON",
        "0 0 5-1 * *",
        "1/2 * * * *",
    ],
)
def test_invalid_or_unsupported_cron_forms_fail_closed(expression: str) -> None:
    with pytest.raises(DefinitionError):
        normalize_collection_schedule(expression)


def test_hourly_stepped_daily_weekly_monthly_and_leap_day() -> None:
    stepped = collection_occurrences_between(
        config("*/15 6 * * *", timezone="UTC"),
        "2026-01-01T06:00:00Z",
        "2026-01-01T07:00:00Z",
    )
    assert [item["scheduled_for"] for item in stepped] == [
        "2026-01-01T06:00:00Z",
        "2026-01-01T06:15:00Z",
        "2026-01-01T06:30:00Z",
        "2026-01-01T06:45:00Z",
    ]

    weekly = collection_occurrences_between(
        config("0 16 * * 1,5"), "2024-02-26T00:00:00Z", "2024-03-05T00:00:00Z"
    )
    assert [item["scheduled_for"] for item in weekly] == [
        "2024-02-26T22:00:00Z",
        "2024-03-01T22:00:00Z",
        "2024-03-04T22:00:00Z",
    ]

    leap = collection_occurrences_between(
        config("0 6 29 2 *"), "2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"
    )
    assert [item["scheduled_for"] for item in leap] == ["2024-02-29T12:00:00Z"]


def test_daily_interval_and_year_boundaries() -> None:
    records = collection_occurrences_between(
        config(),
        datetime(2026, 12, 31, 11, tzinfo=UTC),
        datetime(2027, 1, 2, 12, tzinfo=UTC),
    )
    assert [record["scheduled_for"] for record in records] == [
        "2026-12-31T12:00:00Z",
        "2027-01-01T12:00:00Z",
    ]


def test_spring_gap_advances_to_first_valid_instant_with_marker() -> None:
    records = collection_occurrences_between(
        config("30 2 * * *"), "2026-03-08T06:00:00Z", "2026-03-08T10:00:00Z"
    )
    assert len(records) == 1
    assert records[0]["scheduled_for"] == "2026-03-08T08:00:00Z"
    assert records[0]["effective_local"] == "2026-03-08T03:00:00"
    assert records[0]["adjustment"] == {
        "kind": "gap_advanced",
        "from_local": "2026-03-08T02:30:00",
        "to_local": "2026-03-08T03:00:00",
    }


def test_fall_fold_uses_first_occurrence_once() -> None:
    records = collection_occurrences_between(
        config("30 1 * * *"), "2026-11-01T05:00:00Z", "2026-11-01T09:00:00Z"
    )
    assert len(records) == 1
    assert records[0]["scheduled_for"] == "2026-11-01T06:30:00Z"
    assert records[0]["adjustment"] is None


def test_due_accepts_database_row_shape_and_respects_policy() -> None:
    row = {
        "timezone": "America/Chicago",
        "schedule_json": '{"version":2,"kind":"cron","expression":"0 6 * * *"}',
        "enabled": 1,
        "max_lateness_seconds": 3600,
        "catch_up_policy": "bounded",
        "max_lookback_seconds": 86400,
    }
    now = "2026-01-10T12:30:00Z"
    records = collection_due_occurrences(row, now)
    assert [record["scheduled_for"] for record in records] == ["2026-01-10T12:00:00Z"]
    assert records[0]["lateness_seconds"] == 1800
    assert collection_due_occurrences(
        row, now, completed_scheduled_for=["2026-01-10T12:00:00Z"]
    ) == []
    assert collection_due_occurrences(row, "2026-01-10T13:00:01Z") == []

    latest = config(
        max_lateness_seconds=3 * 86400,
        catch_up={"policy": "latest", "max_lookback_seconds": 3 * 86400},
    )
    records = collection_due_occurrences(latest, "2026-01-10T18:00:00Z")
    assert [record["scheduled_for"] for record in records] == ["2026-01-10T12:00:00Z"]
