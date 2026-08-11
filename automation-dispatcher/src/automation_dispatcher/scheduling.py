"""Deterministic dispatcher-owned collection schedule evaluation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .definitions import CATCH_UP_POLICIES, DefinitionError, WEEKDAYS, WEEKDAY_ALIASES


UTC = timezone.utc
_CRON_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_SCHEDULE_KEYS = ("schedule", "schedule_json")
_TIME_RE = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)(?::(?P<second>[0-5]\d))?$")


def _utc_datetime(value: datetime | str, field: str) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_text(value: datetime) -> str:
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def _round_trips(naive: datetime, zone: ZoneInfo, fold: int) -> tuple[bool, datetime]:
    candidate = naive.replace(tzinfo=zone, fold=fold)
    utc = candidate.astimezone(UTC)
    returned = utc.astimezone(zone)
    valid = returned.replace(tzinfo=None) == naive and returned.fold == fold
    return valid, utc


def _resolve_wall_time(naive: datetime, zone: ZoneInfo) -> tuple[datetime, dict[str, str] | None]:
    """Resolve a local wall time under the existing deterministic DST policy."""

    candidates: list[datetime] = []
    for fold in (0, 1):
        valid, instant = _round_trips(naive, zone, fold)
        if valid and instant not in candidates:
            candidates.append(instant)
    if candidates:
        return min(candidates), None

    probe = naive
    for _ in range(2 * 24 * 60 * 60):
        probe += timedelta(seconds=1)
        candidates = []
        for fold in (0, 1):
            valid, instant = _round_trips(probe, zone, fold)
            if valid and instant not in candidates:
                candidates.append(instant)
        if candidates:
            return min(candidates), {
                "kind": "gap_advanced",
                "from_local": naive.isoformat(timespec="seconds"),
                "to_local": probe.isoformat(timespec="seconds"),
            }
    raise ValueError(f"could not resolve local time {naive.isoformat()} in {zone.key}")


def _dates_between(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _integer(value: str, field: str, minimum: int, maximum: int) -> int:
    if not value.isascii() or not value.isdigit():
        raise DefinitionError(f"cron {field} contains an unsupported value: {value!r}")
    result = int(value)
    if not minimum <= result <= maximum:
        raise DefinitionError(f"cron {field} value must be between {minimum} and {maximum}")
    return result


def _expand_cron_field(token: str, index: int) -> set[int]:
    minimum, maximum = _CRON_LIMITS[index]
    field = ("minute", "hour", "day-of-month", "month", "day-of-week")[index]
    values: set[int] = set()
    for part in token.split(","):
        if not part:
            raise DefinitionError(f"cron {field} contains an empty list item")
        base, separator, raw_step = part.partition("/")
        if separator:
            if "/" in raw_step or not raw_step.isascii() or not raw_step.isdigit() or int(raw_step) < 1:
                raise DefinitionError(f"cron {field} step must be a positive integer")
            step = int(raw_step)
        else:
            step = 1
        if base == "*":
            start, stop = minimum, maximum
        elif "-" in base:
            raw_start, dash, raw_stop = base.partition("-")
            if not dash or "-" in raw_stop:
                raise DefinitionError(f"cron {field} range is invalid")
            start = _integer(raw_start, field, minimum, maximum)
            stop = _integer(raw_stop, field, minimum, maximum)
            if start > stop:
                raise DefinitionError(f"cron {field} ranges must be ascending")
        else:
            if separator:
                raise DefinitionError(f"cron {field} steps require * or an explicit range")
            start = stop = _integer(base, field, minimum, maximum)
        values.update(range(start, stop + 1, step))
    if index == 4 and 7 in values:
        values.remove(7)
        values.add(0)
    return values


def _canonical_cron_expression(expression: Any) -> tuple[str, tuple[set[int], ...]]:
    if not isinstance(expression, str) or not expression.strip():
        raise DefinitionError("collection schedule expression must be a non-empty string")
    fields = expression.split()
    if len(fields) != 5:
        raise DefinitionError("collection schedule must use exactly five cron fields")
    expanded = tuple(_expand_cron_field(token, index) for index, token in enumerate(fields))
    if expanded[2] != set(range(1, 32)) and expanded[4] != set(range(0, 7)):
        raise DefinitionError(
            "collection schedule must not constrain both day-of-month and day-of-week"
        )
    return " ".join(fields), expanded


def _preset_expression(value: Mapping[str, Any]) -> str:
    preset = str(value.get("preset", value.get("frequency", ""))).strip().lower()
    if preset not in {"daily", "weekly"}:
        raise DefinitionError("collection schedule preset must be daily or weekly")
    raw_time = value.get("time", value.get("local_time"))
    if not isinstance(raw_time, str) or not (match := _TIME_RE.fullmatch(raw_time.strip())):
        raise DefinitionError("collection schedule preset time must be HH:MM[:00]")
    if match.group("second") not in (None, "00"):
        raise DefinitionError("five-field cron presets cannot represent non-zero seconds")
    minute = int(match.group("minute"))
    hour = int(match.group("hour"))
    if preset == "daily":
        if value.get("weekdays", value.get("days", value.get("weekday"))) not in (None, [], ()):
            raise DefinitionError("daily collection schedule presets must not specify weekdays")
        return f"{minute} {hour} * * *"
    supplied = value.get("weekdays", value.get("days", value.get("weekday")))
    if isinstance(supplied, (str, int)):
        supplied = [supplied]
    if not isinstance(supplied, (list, tuple)) or not supplied:
        raise DefinitionError("weekly collection schedule presets require weekdays")
    cron_days: set[int] = set()
    for item in supplied:
        if isinstance(item, bool):
            raise DefinitionError("weekly collection schedule weekday is invalid")
        if isinstance(item, int):
            if not 0 <= item <= 6:
                raise DefinitionError("integer weekdays must be between 0 and 6")
            weekday = item
        else:
            day = WEEKDAY_ALIASES.get(str(item).strip().lower())
            if day is None:
                raise DefinitionError(f"unknown weekday: {item}")
            weekday = WEEKDAYS.index(day)
        cron_days.add((weekday + 1) % 7)
    return f"{minute} {hour} * * {','.join(str(day) for day in sorted(cron_days))}"


def normalize_collection_schedule(value: Any) -> dict[str, Any]:
    """Normalize cron or a daily/weekly preset to canonical schedule JSON."""

    if isinstance(value, str):
        expression = value
        version = 2
        kind = "cron"
    elif isinstance(value, Mapping):
        if "preset" in value or "frequency" in value:
            expression = _preset_expression(value)
            version = 2
            kind = "cron"
        else:
            version = value.get("version", 2)
            kind = str(value.get("kind", "cron")).strip().lower()
            expression = value.get("expression")
    else:
        raise DefinitionError("collection schedule must be cron text or an object")
    if isinstance(version, bool) or not isinstance(version, int) or version != 2:
        raise DefinitionError("collection schedule version must be 2")
    if kind != "cron":
        raise DefinitionError("collection schedule kind must be cron")
    canonical, _ = _canonical_cron_expression(expression)
    return {"version": 2, "kind": "cron", "expression": canonical}


def _schedule_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    supplied = [key for key in _SCHEDULE_KEYS if key in config]
    if len(supplied) != 1:
        raise DefinitionError("dispatcher config must specify exactly one of schedule or schedule_json")
    schedule = config[supplied[0]]
    if supplied[0] == "schedule_json" and isinstance(schedule, str):
        try:
            schedule = json.loads(schedule)
        except json.JSONDecodeError as exc:
            raise DefinitionError("schedule_json must contain valid JSON") from exc
    return normalize_collection_schedule(schedule)


def _collection_config(config: Mapping[str, Any], *, due: bool) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        try:
            config = dict(config)
        except (TypeError, ValueError) as exc:
            raise DefinitionError("dispatcher schedule config must be an object") from exc
    timezone_name = config.get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise DefinitionError("dispatcher timezone must be an IANA timezone name")
    timezone_name = timezone_name.strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DefinitionError(f"unknown IANA timezone: {timezone_name}") from exc
    enabled = config.get("enabled", True)
    if isinstance(enabled, int) and enabled in (0, 1):
        enabled = bool(enabled)
    if not isinstance(enabled, bool):
        raise DefinitionError("dispatcher enabled must be a boolean")
    normalized: dict[str, Any] = {
        "timezone": timezone_name,
        "schedule": _schedule_from_config(config),
        "enabled": enabled,
    }
    if not due:
        return normalized
    lateness = config.get("max_lateness_seconds")
    if isinstance(lateness, bool) or not isinstance(lateness, int) or lateness < 0:
        raise DefinitionError("max_lateness_seconds must be a non-negative integer")
    catch_up = config.get("catch_up")
    if catch_up is None:
        catch_up = {
            "policy": config.get("catch_up_policy"),
            "max_lookback_seconds": config.get("max_lookback_seconds"),
        }
    if not isinstance(catch_up, Mapping):
        raise DefinitionError("catch_up must be an object")
    policy = catch_up.get("policy")
    if not isinstance(policy, str) or policy not in CATCH_UP_POLICIES:
        raise DefinitionError(f"unsupported catch_up.policy: {policy}")
    lookback = catch_up.get("max_lookback_seconds")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 0:
        raise DefinitionError("catch_up.max_lookback_seconds must be a non-negative integer")
    normalized["max_lateness_seconds"] = lateness
    normalized["catch_up"] = {"policy": policy, "max_lookback_seconds": lookback}
    return normalized


def collection_occurrences_between(
    config: Mapping[str, Any],
    start_utc: datetime | str,
    end_utc: datetime | str,
) -> list[dict[str, Any]]:
    """Return collection occurrences in the half-open UTC interval ``[start, end)``."""

    normalized = _collection_config(config, due=False)
    start = _utc_datetime(start_utc, "start_utc")
    end = _utc_datetime(end_utc, "end_utc")
    if end < start:
        raise ValueError("end_utc must not be earlier than start_utc")
    if end == start or not normalized["enabled"]:
        return []
    zone = ZoneInfo(normalized["timezone"])
    expression = normalized["schedule"]["expression"]
    _, fields = _canonical_cron_expression(expression)
    minutes, hours, days_of_month, months, days_of_week = fields
    first_date = (start - timedelta(days=2)).astimezone(zone).date()
    last_date = (end + timedelta(days=2)).astimezone(zone).date()
    records: list[dict[str, Any]] = []
    seen: set[datetime] = set()
    for local_date in _dates_between(first_date, last_date):
        if local_date.month not in months or local_date.day not in days_of_month:
            continue
        cron_weekday = (local_date.weekday() + 1) % 7
        if cron_weekday not in days_of_week:
            continue
        for hour in sorted(hours):
            for minute in sorted(minutes):
                intended = datetime(local_date.year, local_date.month, local_date.day, hour, minute)
                scheduled, adjustment = _resolve_wall_time(intended, zone)
                if scheduled in seen or not (start <= scheduled < end):
                    continue
                seen.add(scheduled)
                records.append(
                    {
                        "scheduled_for": _utc_text(scheduled),
                        "intended_local": intended.isoformat(timespec="seconds"),
                        "effective_local": _local_text(scheduled.astimezone(zone)),
                        "timezone": normalized["timezone"],
                        "adjustment": adjustment,
                    }
                )
    records.sort(key=lambda record: record["scheduled_for"])
    return records


def collection_due_occurrences(
    config: Mapping[str, Any],
    now_utc: datetime | str,
    start_utc: datetime | str | None = None,
    *,
    last_checked_utc: datetime | str | None = None,
    completed_scheduled_for: Iterable[datetime | str] = (),
    max_occurrences: int | None = None,
) -> list[dict[str, Any]]:
    """Return collection occurrences due under dispatcher catch-up policy."""

    normalized = _collection_config(config, due=True)
    if not normalized["enabled"]:
        return []
    now = _utc_datetime(now_utc, "now_utc")
    catch_up = normalized["catch_up"]
    window_seconds = min(
        normalized["max_lateness_seconds"], catch_up["max_lookback_seconds"]
    )
    beginning = now - timedelta(seconds=window_seconds)
    supplied_start = last_checked_utc if last_checked_utc is not None else start_utc
    if supplied_start is not None:
        beginning = max(beginning, _utc_datetime(supplied_start, "start_utc"))
    records = collection_occurrences_between(
        normalized, beginning, now + timedelta(microseconds=1)
    )
    completed = {
        _utc_text(_utc_datetime(value, "completed_scheduled_for"))
        for value in completed_scheduled_for
    }
    due_records: list[dict[str, Any]] = []
    for record in records:
        if record["scheduled_for"] in completed:
            continue
        scheduled = _utc_datetime(record["scheduled_for"], "scheduled_for")
        enriched = dict(record)
        enriched["lateness_seconds"] = int((now - scheduled).total_seconds())
        due_records.append(enriched)
    if catch_up["policy"] in {"none", "latest"} and due_records:
        due_records = [due_records[-1]]
    if max_occurrences is not None:
        if isinstance(max_occurrences, bool) or not isinstance(max_occurrences, int) or max_occurrences < 0:
            raise ValueError("max_occurrences must be a non-negative integer")
        due_records = due_records[-max_occurrences:] if max_occurrences else []
    return due_records


def occurrences_between(
    config: Mapping[str, Any], start_utc: datetime | str, end_utc: datetime | str
) -> list[dict[str, Any]]:
    """Compatibility name for dispatcher-owned collection occurrence evaluation."""

    return collection_occurrences_between(config, start_utc, end_utc)


def due_occurrences(
    config: Mapping[str, Any],
    now_utc: datetime | str,
    start_utc: datetime | str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Compatibility name for dispatcher-owned collection due evaluation."""

    return collection_due_occurrences(config, now_utc, start_utc, **kwargs)


__all__ = [
    "collection_due_occurrences",
    "collection_occurrences_between",
    "due_occurrences",
    "normalize_collection_schedule",
    "occurrences_between",
]
