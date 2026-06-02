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


def test_deterministic_planner_infers_popularity_proxy_for_ranking() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical"},
            {"name": "Platform", "inferred_type": "categorical"},
            {"name": "Global_Sales", "inferred_type": "numeric"},
            {"name": "Critic_Score", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Show me the most popular videogames.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    chart = next(step for step in plan["steps"] if step["tool"] == "create_chart")
    assert transform["arguments"] == {
        "select": ["Name", "Global_Sales"],
        "sort_by": "Global_Sales",
        "sort_desc": True,
        "limit": 10,
    }
    assert chart["arguments"]["x"] == "Name"
    assert chart["arguments"]["y"] == "Global_Sales"
    assert "popularity proxy" in plan["assumptions"][0]


def test_deterministic_planner_asks_for_clarification_without_proxy_column() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical"},
            {"name": "Genre", "inferred_type": "categorical"},
        ]
    }

    plan = AnalystPlanner().plan("Show me the most popular videogames.", profile, [])

    assert plan["clarification_required"] is True
    assert "Which column should I use?" in plan["clarifying_question"]
    assert plan["candidate_columns"] == ["Name", "Genre"]


def test_deterministic_planner_does_not_guess_ambiguous_top_metric() -> None:
    profile = {
        "columns": [
            {"name": "Customer", "inferred_type": "categorical"},
            {"name": "Age", "inferred_type": "numeric"},
            {"name": "Tenure", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Show me the top customers.", profile, [])

    assert plan["clarification_required"] is True
    assert "Which numeric column should define this ranking?" in plan["clarifying_question"]
    assert plan["candidate_columns"] == ["Age", "Tenure"]


def test_deterministic_planner_recognizes_date_like_numeric_columns() -> None:
    profile = {
        "columns": [
            {"name": "Game_Title", "inferred_type": "categorical"},
            {"name": "Release_Year", "inferred_type": "numeric"},
            {"name": "Global_Sales", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Show me the latest games.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["select"] == ["Game_Title", "Release_Year"]
    assert transform["arguments"]["sort_by"] == "Release_Year"
    assert transform["arguments"]["sort_desc"] is True


def test_deterministic_planner_filters_semantic_ranking_by_publisher_value() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical", "top_values": [{"value": "Gran Turismo", "count": 1}]},
            {"name": "Publisher", "inferred_type": "categorical", "top_values": [{"value": "Sony Computer Entertainment", "count": 2}]},
            {"name": "Genre", "inferred_type": "categorical", "top_values": [{"value": "Sports", "count": 1}]},
            {"name": "Global_Sales", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Give me a graph with the most popular Sony video games of all time.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["filters"] == [{"column": "Publisher", "op": "contains", "value": "sony"}]
    assert transform["arguments"]["select"] == ["Name", "Publisher", "Global_Sales"]
    assert "Publisher contains sony" in plan["assumptions"][1]


def test_deterministic_planner_filters_semantic_ranking_by_genre_value() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical", "top_values": [{"value": "FIFA 10", "count": 1}]},
            {"name": "Publisher", "inferred_type": "categorical", "top_values": [{"value": "Electronic Arts", "count": 2}]},
            {"name": "Genre", "inferred_type": "categorical", "top_values": [{"value": "Sports", "count": 2}]},
            {"name": "Global_Sales", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Give me a graph with the most popular sports video games of all time.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["filters"] == [{"column": "Genre", "op": "contains", "value": "Sports"}]
    assert transform["arguments"]["select"] == ["Name", "Genre", "Global_Sales"]


def test_deterministic_planner_filters_category_even_when_it_is_display_label() -> None:
    profile = {
        "columns": [
            {"name": "color", "inferred_type": "categorical", "top_values": [{"value": "red", "count": 5}, {"value": "white", "count": 5}]},
            {"name": "quality", "inferred_type": "numeric"},
        ]
    }

    plan = AnalystPlanner().plan("Show me the best red wines.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["filters"] == [{"column": "color", "op": "contains", "value": "red"}]
    assert transform["arguments"]["select"] == ["color", "quality"]


def test_deterministic_planner_treats_worst_selling_as_lowest_sales() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical"},
            {"name": "Genre", "inferred_type": "categorical", "top_values": [{"value": "Sports", "count": 2}]},
            {"name": "Global_Sales", "inferred_type": "numeric", "missing_count": 0},
            {"name": "Critic_Score", "inferred_type": "numeric", "missing_count": 0},
        ]
    }

    plan = AnalystPlanner().plan("Give me a graph with the worst selling videogames of all time.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    chart = next(step for step in plan["steps"] if step["tool"] == "create_chart")
    assert transform["arguments"]["sort_by"] == "Global_Sales"
    assert transform["arguments"]["sort_desc"] is False
    assert chart["arguments"]["y"] == "Global_Sales"
    assert "popularity proxy" in plan["assumptions"][0]


def test_deterministic_planner_excludes_missing_metric_values_before_ranking() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical"},
            {"name": "Global_Sales", "inferred_type": "numeric", "missing_count": 3},
        ]
    }

    plan = AnalystPlanner().plan("Show the worst selling video games.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["filters"] == [{"column": "Global_Sales", "op": "not_null", "value": None}]
    assert "excluded 3 row(s) with missing Global_Sales" in plan["assumptions"][1]


def test_deterministic_planner_adds_year_range_filter_to_ranking() -> None:
    profile = {
        "columns": [
            {"name": "Name", "inferred_type": "categorical"},
            {"name": "Year", "inferred_type": "numeric", "missing_count": 0, "numeric": {"min": 1980, "max": 2020}},
            {"name": "Global_Sales", "inferred_type": "numeric", "missing_count": 0},
        ]
    }

    plan = AnalystPlanner().plan("Show the best selling video games between 2000 and 2010.", profile, [])

    transform = next(step for step in plan["steps"] if step["tool"] == "run_transform")
    assert transform["arguments"]["filters"] == [
        {"column": "Year", "op": ">=", "value": 2000},
        {"column": "Year", "op": "<=", "value": 2010},
    ]
    assert transform["arguments"]["select"] == ["Name", "Year", "Global_Sales"]
