import json
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
            sort_by = next((col for col in numeric_cols if col.lower() in lowered), numeric_cols[0])
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
            y = next((col for col in numeric_cols if col.lower() in lowered), numeric_cols[0])
            group = next((col for col in categorical_cols if col.lower() in lowered), categorical_cols[0] if categorical_cols else columns[0])
            sql = f'SELECT "{group}", AVG("{y}") AS avg_{y.replace(" ", "_")} FROM dataset GROUP BY "{group}" ORDER BY avg_{y.replace(" ", "_")} DESC'
            chart = {"chart_type": "bar", "x": group, "y": f"avg_{y.replace(' ', '_')}", "title": f"Average {y} by {group}"}
        elif any(word in lowered for word in ["plot", "chart", "trend", "show"]) and numeric_cols:
            x = date_cols[0] if date_cols else (categorical_cols[0] if categorical_cols else columns[0])
            y = next((col for col in numeric_cols if col.lower() in lowered), numeric_cols[0])
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
                    "You are a governed tabular analyst planner. Call only the provided tools. "
                    "Never request arbitrary Python, DDL/DML, file access, network access, or unbounded outputs. "
                    "Use run_safe_sql for read-only tabular queries and create_chart only after a query when useful."
                ),
                input=f"Dataset columns: {allowed_columns}\nQuality issue count: {len(issues)}\nQuestion: {question}",
                tools=tools,
            )
            steps = []
            for item in getattr(response, "output", []) or []:
                if getattr(item, "type", None) == "function_call":
                    steps.append({"tool": item.name, "arguments": json.loads(item.arguments or "{}")})
            if not steps:
                return super().plan(question, profile, issues)
            if steps[-1]["tool"] != "summarize_result":
                steps.append({"tool": "summarize_result", "arguments": {}})
            return {"blocked": False, "steps": steps}
        except Exception:
            return super().plan(question, profile, issues)


def build_planner(settings: Settings) -> AnalystPlanner:
    return OpenAIPlanner(settings) if settings.llm_provider == "openai" else AnalystPlanner()


def _tool_schemas(columns: list[str]) -> list[dict[str, Any]]:
    column_enum = columns or ["dataset_column"]
    return [
        {
            "type": "function",
            "name": "profile_dataset",
            "description": "Return dataset schema, column types, missingness, preview rows, and summary statistics.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        },
        {
            "type": "function",
            "name": "detect_data_quality_issues",
            "description": "Detect missingness, duplicates, outliers, constants, and suspicious categorical columns.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        },
        {
            "type": "function",
            "name": "run_safe_sql",
            "description": "Run one read-only SELECT/CTE query over the table named dataset. Never use DDL, DML, files, network, COPY, PRAGMA, INSTALL, LOAD, or multiple statements.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "run_transform",
            "description": "Run a bounded dataframe transformation with optional select, filters, group-by aggregations, sort, and limit. Prefer this for top-N, simple filters, and deterministic tabular transformations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "select": {"type": "array", "items": {"type": "string", "enum": column_enum}},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string", "enum": column_enum},
                                "op": {"type": "string", "enum": ["==", "!=", ">", ">=", "<", "<=", "contains"]},
                                "value": {"type": ["string", "number", "boolean"]},
                            },
                            "required": ["column", "op", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "group_by": {"type": "array", "items": {"type": "string", "enum": column_enum}},
                    "aggregations": {
                        "type": "object",
                        "additionalProperties": {"type": "string", "enum": ["sum", "mean", "median", "min", "max", "count"]},
                    },
                    "sort_by": {"type": "string", "enum": column_enum},
                    "sort_desc": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "create_chart",
            "description": "Create a validated Plotly chart from the most recent result table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "scatter", "histogram", "box", "heatmap"]},
                    "x": {"type": "string", "enum": column_enum},
                    "y": {"type": "string", "enum": column_enum},
                    "color": {"type": "string", "enum": column_enum},
                    "title": {"type": "string"},
                },
                "required": ["chart_type", "x", "y", "title"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "summarize_result",
            "description": "Create the final structured analyst answer after tools have run.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        },
    ]
