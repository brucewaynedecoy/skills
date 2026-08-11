from automation_dispatcher.routing import check_route


def test_attested_mismatch_fails_closed() -> None:
    result = check_route(
        {"task_id": "configured-task"},
        {"task_id": {"value": "other-task", "source": "runtime", "assurance": "attested"}},
        {"task_id": {"required": True, "minimum_assurance": "attested"}},
    )
    assert result["ok"] is False
    assert result["outcome"] == "route_mismatch"
    assert result["mismatches"][0]["field"] == "task_id"


def test_matching_value_below_minimum_is_unattested() -> None:
    result = check_route(
        {"task_id": "task"},
        {"task_id": {"value": "task", "source": "declared"}},
        {"task_id": "verified_config"},
    )
    assert result["outcome"] == "route_unattested"
    assert result["unattested"][0]["observed"]["assurance"] == "declared"


def test_unknown_optional_identity_is_recorded_and_allowed() -> None:
    result = check_route(
        {"task_id": "task", "host_id": None},
        {
            "task_id": {"value": "task", "assurance": "attested", "source": "runtime"},
            "host_id": {"value": None, "source": "unknown", "assurance": "unknown"},
        },
        {
            "task_id": "attested",
            "host_id": {"required": False, "minimum_assurance": "attested", "allow_unknown": True},
        },
    )
    assert result["ok"] is True
    assert result["outcome"] == "ok"
    assert result["checks"][0]["field"] == "host_id"
    assert result["checks"][0]["observed"]["assurance"] == "unknown"


def test_low_assurance_conflict_is_unattested_not_mismatch() -> None:
    result = check_route(
        {"working_directory": "/expected"},
        {"working_directory": {"value": "/prompt-value", "source": "declared"}},
        {"working_directory": "attested"},
    )
    assert result["outcome"] == "route_unattested"
    assert not result["mismatches"]
