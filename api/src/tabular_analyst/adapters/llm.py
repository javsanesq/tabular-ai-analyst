import json
import re
from typing import Any

from tabular_analyst.core.config import Settings


class AnalystPlanner:
    def plan(self, question: str, profile: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
        lowered = question.lower()
        if any(term in lowered for term in ["delete", "drop table", "run python", "read local", "open /", "system prompt", "overwrite", "export", "install", "copy to"]):
            return {"blocked": True, "reason": "Unsafe or out-of-scope request blocked by governed planner.", "steps": []}
        columns = [col["name"] for col in profile.get("columns", [])]
        numeric_cols = [col["name"] for col in profile.get("columns", []) if col.get("inferred_type") == "numeric"]
        date_cols = [col["name"] for col in profile.get("columns", []) if col.get("inferred_type") == "datetime" or col["name"].lower() in {"year", "date"}]
        categorical_cols = [col["name"] for col in profile.get("columns", []) if col.get("inferred_type") == "categorical"]
        steps: list[dict[str, Any]] = [{"tool": "profile_dataset", "arguments": {}}]
        if "issue" in lowered or "quality" in lowered or "missing" in lowered:
            steps.append({"tool": "detect_data_quality_issues", "arguments": {}})
        sql = "SELECT * FROM dataset LIMIT 20"
        chart = None
        if any(term in lowered for term in ["top", "highest", "largest", "sort"]) and numeric_cols:
            sort_by = _mentioned_column(numeric_cols, lowered) or numeric_cols[0]
            limit = 5
            for candidate in [3, 5, 10]:
                if str(candidate) in lowered:
                    limit = candidate
                    break
            selected = []
            if categorical_cols:
                selected.append(categorical_cols[0])
            selected.append(sort_by)
            steps.append({"tool": "run_transform", "arguments": {"select": selected, "sort_by": sort_by, "sort_desc": True, "limit": limit}})
        elif ("average" in lowered or "mean" in lowered) and numeric_cols:
            y = _mentioned_column(numeric_cols, lowered) or numeric_cols[0]
            group = _mentioned_column(categorical_cols, lowered) or (categorical_cols[0] if categorical_cols else columns[0])
            sql = f'SELECT "{group}", AVG("{y}") AS avg_{y.replace(" ", "_")} FROM dataset GROUP BY "{group}" ORDER BY avg_{y.replace(" ", "_")} DESC'
            chart = {"chart_type": "bar", "x": group, "y": f"avg_{y.replace(' ', '_')}", "title": f"Average {y} by {group}"}
        elif any(word in lowered for word in ["plot", "chart", "trend", "show"]) and numeric_cols:
            x = date_cols[0] if date_cols else (categorical_cols[0] if categorical_cols else columns[0])
            y = _mentioned_column(numeric_cols, lowered) or numeric_cols[0]
            chart_type = "line" if x in date_cols or x.lower() == "year" else "bar"
            sql = f'SELECT "{x}", "{y}" FROM dataset WHERE "{y}" IS NOT NULL ORDER BY "{x}" LIMIT 200'
            chart = {"chart_type": chart_type, "x": x, "y": y, "title": f"{y} by {x}"}
        if not any(step["tool"] == "run_transform" for step in steps):
            steps.append({"tool": "run_safe_sql", "arguments": {"sql": sql}})
        if chart:
            steps.append({"tool": "create_chart", "arguments": chart})
        steps.append({"tool": "summarize_result", "arguments": {}})
        return {"blocked": False, "steps": steps}


class OpenAIPlanner(AnalystPlanner):
    def __init__(self, settings: Settings):
        self.settings = settings

    def plan(self, question: str, profile: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            return super().plan(question, profile, issues)
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.settings.openai_api_key)
            allowed_columns = [col["name"] for col in profile.get("columns", [])]
            tools = _tool_schemas(allowed_columns)
            response = client.responses.create(
                model=self.settings.openai_model,
                instructions=(
                    "You are a governed tabular analyst planner. Return tool calls only from the provided tools. "
                    "Plan a complete analysis using the minimum safe sequence of tools. "
                    "Never request arbitrary Python, DDL/DML, file access, network access, or unbounded outputs. "
                    "Use run_safe_sql for read-only tabular queries, run_transform for bounded row operations, "
                    "create_chart only after a table-producing step when useful, and summarize_result last."
                ),
                input=f"Dataset columns: {allowed_columns}\nQuality issue count: {len(issues)}\nQuestion: {question}",
                tools=tools,
                parallel_tool_calls=False,
            )
            steps = []
            for item in getattr(response, "output", []) or []:
                if getattr(item, "type", None) == "function_call":
                    args = json.loads(item.arguments or "{}")
                    steps.append({"tool": item.name, "arguments": _normalize_tool_arguments(item.name, args)})
            if not steps:
                return super().plan(question, profile, issues)
            if steps[-1]["tool"] != "summarize_result":
                steps.append({"tool": "summarize_result", "arguments": {}})
            return {"blocked": False, "steps": steps}
        except Exception:
            return super().plan(question, profile, issues)


def build_planner(settings: Settings) -> AnalystPlanner:
    return OpenAIPlanner(settings) if settings.llm_provider == "openai" else AnalystPlanner()


def _mentioned_column(columns: list[str], lowered_question: str) -> str | None:
    for column in columns:
        pattern = rf"(?<![a-z0-9_]){re.escape(column.lower())}(?![a-z0-9_])"
        if re.search(pattern, lowered_question):
            return column
    return None


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties.keys()), "additionalProperties": False}


def _nullable_string(enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": ["string", "null"]}
    if enum:
        schema["enum"] = [*enum, None]
    return schema


def _nullable_string_array(enum: list[str] | None = None) -> dict[str, Any]:
    items: dict[str, Any] = {"type": "string"}
    if enum:
        items["enum"] = enum
    return {"type": ["array", "null"], "items": items}


def _normalize_tool_arguments(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in args.items() if value is not None}
    if tool == "run_transform" and isinstance(cleaned.get("aggregations"), list):
        cleaned["aggregations"] = {
            row["column"]: row["function"]
            for row in cleaned["aggregations"]
            if isinstance(row, dict) and row.get("column") and row.get("function")
        }
    return cleaned


def _tool_schemas(columns: list[str]) -> list[dict[str, Any]]:
    column_enum = columns or ["dataset_column"]
    filter_schema = _strict_object({
        "column": {"type": "string", "enum": column_enum},
        "op": {"type": "string", "enum": ["==", "!=", ">", ">=", "<", "<=", "contains"]},
        "value": {"type": ["string", "number", "boolean", "null"]},
    })
    aggregation_schema = _strict_object({
        "column": {"type": "string", "enum": column_enum},
        "function": {"type": "string", "enum": ["sum", "mean", "median", "min", "max", "count"]},
    })
    return [
        {
            "type": "function",
            "name": "profile_dataset",
            "description": "Return dataset schema, column types, missingness, preview rows, and summary statistics.",
            "parameters": _strict_object({}),
            "strict": True,
        },
        {
            "type": "function",
            "name": "detect_data_quality_issues",
            "description": "Detect missingness, duplicates, outliers, constants, and suspicious categorical columns.",
            "parameters": _strict_object({}),
            "strict": True,
        },
        {
            "type": "function",
            "name": "run_safe_sql",
            "description": "Run one read-only SELECT/CTE query over the table named dataset. Never use DDL, DML, files, network, COPY, PRAGMA, INSTALL, LOAD, or multiple statements.",
            "parameters": _strict_object({"sql": {"type": "string"}}),
            "strict": True,
        },
        {
            "type": "function",
            "name": "run_transform",
            "description": "Run a bounded dataframe transformation with optional select, filters, group-by aggregations, sort, and limit. Prefer this for top-N, simple filters, and deterministic tabular transformations.",
            "parameters": _strict_object({
                "select": _nullable_string_array(column_enum),
                "filters": {"type": ["array", "null"], "items": filter_schema},
                "group_by": _nullable_string_array(column_enum),
                "aggregations": {"type": ["array", "null"], "items": aggregation_schema},
                "sort_by": _nullable_string(column_enum),
                "sort_desc": {"type": ["boolean", "null"]},
                "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 500},
            }),
            "strict": True,
        },
        {
            "type": "function",
            "name": "create_chart",
            "description": "Create a validated Plotly chart from the most recent result table. x, y, and color are validated against the actual result columns by the backend, so derived SQL aliases are allowed.",
            "parameters": _strict_object({
                "chart_type": {"type": "string", "enum": ["bar", "line", "scatter", "histogram", "box", "heatmap"]},
                "x": _nullable_string(),
                "y": _nullable_string(),
                "color": _nullable_string(),
                "title": {"type": "string"},
            }),
            "strict": True,
        },
        {
            "type": "function",
            "name": "summarize_result",
            "description": "Create the final structured analyst answer after tools have run.",
            "parameters": _strict_object({}),
            "strict": True,
        },
    ]
