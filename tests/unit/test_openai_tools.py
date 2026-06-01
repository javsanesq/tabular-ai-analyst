from tabular_analyst.adapters.llm import AnalystPlanner, _normalize_tool_arguments, _tool_schemas


def _assert_strict_object(schema: dict) -> None:
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())
    for value in schema["properties"].values():
        if isinstance(value, dict) and value.get("type") == "object":
            _assert_strict_object(value)
        if isinstance(value, dict) and value.get("items", {}).get("type") == "object":
            _assert_strict_object(value["items"])


def test_openai_tool_schemas_are_strict_response_compatible() -> None:
    tools = _tool_schemas(["color", "quality", "alcohol"])

    assert {tool["name"] for tool in tools} == {
        "profile_dataset",
        "detect_data_quality_issues",
        "run_safe_sql",
        "run_transform",
        "create_chart",
        "summarize_result",
    }
    for tool in tools:
        assert tool["type"] == "function"
        assert tool["strict"] is True
        _assert_strict_object(tool["parameters"])


def test_openai_tool_argument_normalization_removes_nulls_and_maps_aggregations() -> None:
    args = _normalize_tool_arguments(
        "run_transform",
        {
            "select": None,
            "filters": None,
            "group_by": ["color"],
            "aggregations": [{"column": "alcohol", "function": "mean"}],
            "sort_by": None,
            "sort_desc": None,
            "limit": 20,
        },
    )

    assert args == {
        "group_by": ["color"],
        "aggregations": {"alcohol": "mean"},
        "limit": 20,
    }


def test_deterministic_planner_matches_column_names_without_substring_collisions() -> None:
    profile = {
        "columns": [
            {"name": "color", "inferred_type": "categorical"},
            {"name": "pH", "inferred_type": "numeric"},
            {"name": "sulphates", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Show the largest sulphates values.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["sort_by"] == "sulphates"
