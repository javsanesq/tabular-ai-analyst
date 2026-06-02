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
        date_cols = [
            col["name"]
            for col in profile.get("columns", [])
            if col.get("inferred_type") == "datetime" or _semantic_score(col["name"], "time") > 0
        ]
        categorical_cols = [col["name"] for col in profile.get("columns", []) if col.get("inferred_type") == "categorical"]
        steps: list[dict[str, Any]] = [{"tool": "profile_dataset", "arguments": {}}]
        if "issue" in lowered or "quality" in lowered or "missing" in lowered:
            steps.append({"tool": "detect_data_quality_issues", "arguments": {}})
        semantic_plan = _semantic_plan(lowered, profile, numeric_cols, categorical_cols, date_cols)
        if semantic_plan:
            if semantic_plan.get("clarification_required"):
                return {"blocked": False, "steps": steps, **semantic_plan}
            steps.extend(semantic_plan["steps"])
            steps.append({"tool": "summarize_result", "arguments": {}})
            return {"blocked": False, "steps": steps, "assumptions": semantic_plan.get("assumptions", [])}
        sql = "SELECT * FROM dataset LIMIT 20"
        chart = None
        if any(term in lowered for term in ["top", "highest", "largest", "sort"]) and numeric_cols:
            sort_by = _mentioned_column(numeric_cols, lowered) or _best_semantic_column(numeric_cols, "measure")
            if not sort_by:
                return {
                    "blocked": False,
                    "steps": steps,
                    **_clarify("Which numeric column should define this ranking?", numeric_cols or columns),
                }
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
        deterministic_plan = super().plan(question, profile, issues)
        if deterministic_plan.get("clarification_required") or deterministic_plan.get("assumptions") or not self.settings.openai_api_key:
            return deterministic_plan
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
                    "create_chart only after a table-producing step when useful, and summarize_result last. "
                    "For ambiguous business words such as popular, best, worst, recent, or important, choose the best "
                    "available dataset column as an explicit proxy only when the column clearly supports that meaning. "
                    "Prefer bounded top-N tables and charts for ranking questions."
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
                return deterministic_plan
            if steps[-1]["tool"] != "summarize_result":
                steps.append({"tool": "summarize_result", "arguments": {}})
            return {"blocked": False, "steps": steps}
        except Exception:
            return deterministic_plan


def build_planner(settings: Settings) -> AnalystPlanner:
    return OpenAIPlanner(settings) if settings.llm_provider == "openai" else AnalystPlanner()


def _mentioned_column(columns: list[str], lowered_question: str) -> str | None:
    for column in columns:
        pattern = rf"(?<![a-z0-9_]){re.escape(column.lower())}(?![a-z0-9_])"
        if re.search(pattern, lowered_question):
            return column
    return None


def _semantic_plan(
    lowered_question: str,
    profile: dict[str, Any],
    numeric_cols: list[str],
    categorical_cols: list[str],
    date_cols: list[str],
) -> dict[str, Any] | None:
    columns = [col["name"] for col in profile.get("columns", [])]
    label_col = _best_label_column(categorical_cols) or (categorical_cols[0] if categorical_cols else (columns[0] if columns else None))
    limit = _requested_limit(lowered_question)

    if any(term in lowered_question for term in ["popular", "most played", "most downloaded", "most sold"]):
        proxy = _best_semantic_column(numeric_cols, "popularity")
        if not proxy:
            return _clarify(
                "I can rank popularity only if the dataset has a popularity proxy such as sales, downloads, owners, players, ratings count, reviews, or revenue. Which column should I use?",
                columns,
            )
        return _ranking_plan(label_col, proxy, limit, True, f"I treated {proxy} as the popularity proxy.", "Most popular rows")

    if any(term in lowered_question for term in ["best", "top rated", "highest rated"]):
        proxy = _mentioned_column(numeric_cols, lowered_question) or _best_semantic_column(numeric_cols, "quality")
        if not proxy:
            return _clarify("Which score or rating column should define 'best' for this dataset?", numeric_cols or columns)
        return _ranking_plan(label_col, proxy, limit, True, f"I treated {proxy} as the ranking score.", f"Highest {proxy}")

    if any(term in lowered_question for term in ["worst", "lowest rated", "least rated"]):
        proxy = _mentioned_column(numeric_cols, lowered_question) or _best_semantic_column(numeric_cols, "quality")
        if not proxy:
            return _clarify("Which score or rating column should define 'worst' for this dataset?", numeric_cols or columns)
        return _ranking_plan(label_col, proxy, limit, False, f"I treated {proxy} as the ranking score.", f"Lowest {proxy}")

    if any(term in lowered_question for term in ["recent", "newest", "latest"]):
        proxy = _mentioned_column(date_cols, lowered_question) or _best_semantic_column(date_cols, "time") or (date_cols[0] if date_cols else None)
        if not proxy:
            return _clarify("Which date or year column should define recency for this dataset?", columns)
        return _ranking_plan(label_col, proxy, limit, True, f"I treated {proxy} as the recency column.", f"Most recent rows", chart=False)

    if any(term in lowered_question for term in ["distribution", "histogram"]):
        metric = _mentioned_column(numeric_cols, lowered_question) or _best_semantic_column(numeric_cols, "measure") or (numeric_cols[0] if numeric_cols else None)
        if not metric:
            return _clarify("Which numeric column should I use for the distribution?", columns)
        return {
            "steps": [
                {"tool": "run_safe_sql", "arguments": {"sql": f'SELECT "{metric}" FROM dataset WHERE "{metric}" IS NOT NULL LIMIT 500'}},
                {"tool": "create_chart", "arguments": {"chart_type": "histogram", "x": metric, "y": None, "color": None, "title": f"Distribution of {metric}"}},
            ],
            "assumptions": [f"I used {metric} for the distribution."],
        }

    if any(term in lowered_question for term in ["correlation", "correlate", "relationships between numeric"]):
        if len(numeric_cols) < 2:
            return _clarify("Correlation analysis needs at least two numeric columns. Which numeric columns should I compare?", columns)
        selected = numeric_cols[: min(8, len(numeric_cols))]
        return {
            "steps": [
                {"tool": "run_safe_sql", "arguments": {"sql": "SELECT " + ", ".join(f'"{col}"' for col in selected) + " FROM dataset LIMIT 500"}},
                {"tool": "create_chart", "arguments": {"chart_type": "heatmap", "x": None, "y": None, "color": None, "title": "Numeric correlation heatmap"}},
            ],
            "assumptions": [f"I compared numeric columns: {', '.join(selected)}."],
        }

    return None


def _ranking_plan(label_col: str | None, metric_col: str, limit: int, descending: bool, assumption: str, title: str, chart: bool = True) -> dict[str, Any]:
    selected = []
    if label_col and label_col != metric_col:
        selected.append(label_col)
    selected.append(metric_col)
    steps = [{"tool": "run_transform", "arguments": {"select": selected, "sort_by": metric_col, "sort_desc": descending, "limit": limit}}]
    if chart and label_col:
        steps.append({"tool": "create_chart", "arguments": {"chart_type": "bar", "x": label_col, "y": metric_col, "color": None, "title": title}})
    return {"steps": steps, "assumptions": [assumption]}


def _clarify(question: str, candidate_columns: list[str]) -> dict[str, Any]:
    return {
        "clarification_required": True,
        "clarifying_question": question,
        "candidate_columns": candidate_columns[:12],
    }


def _requested_limit(lowered_question: str) -> int:
    for match in re.finditer(r"\b(?:top|first|best|show)?\s*(\d{1,3})\b", lowered_question):
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value
    return 10


def _best_label_column(categorical_cols: list[str]) -> str | None:
    preferred = ["name", "title", "game", "videogame", "video_game", "movie", "product", "country", "city", "company"]
    for column in categorical_cols:
        tokens = _column_tokens(column)
        if any(token in tokens for token in preferred):
            return column
    return categorical_cols[0] if categorical_cols else None


def _best_semantic_column(columns: list[str], concept: str) -> str | None:
    if not columns:
        return None
    scored = [(column, _semantic_score(column, concept)) for column in columns]
    scored = [(column, score) for column, score in scored if score > 0]
    if not scored:
        return None
    scored.sort(key=lambda row: row[1], reverse=True)
    if len(scored) > 1 and scored[0][1] == scored[1][1]:
        return None
    return scored[0][0]


def _semantic_score(column: str, concept: str) -> int:
    tokens = _column_tokens(column)
    joined = "_".join(tokens)
    weights = {
        "popularity": {
            "global_sales": 12,
            "total_sales": 12,
            "sales": 10,
            "copies_sold": 10,
            "downloads": 10,
            "owners": 9,
            "players": 9,
            "users": 8,
            "installs": 8,
            "plays": 8,
            "visits": 8,
            "review_count": 7,
            "reviews": 6,
            "rating_count": 7,
            "votes": 6,
            "revenue": 6,
            "gross": 5,
            "score": 3,
            "rating": 3,
        },
        "quality": {
            "critic_score": 10,
            "user_score": 10,
            "metacritic": 10,
            "score": 8,
            "rating": 8,
            "review_score": 8,
            "quality": 8,
            "stars": 6,
        },
        "time": {
            "release_date": 10,
            "released": 9,
            "date": 8,
            "year": 8,
            "created_at": 6,
            "updated_at": 5,
        },
        "measure": {
            "sales": 5,
            "revenue": 5,
            "score": 4,
            "rating": 4,
            "price": 4,
            "value": 3,
            "count": 3,
            "total": 2,
        },
    }
    concept_weights = weights.get(concept, {})
    score = 0
    for key, weight in concept_weights.items():
        key_tokens = key.split("_")
        if key == joined:
            score = max(score, weight + 3)
        elif all(token in tokens for token in key_tokens):
            score = max(score, weight)
        elif any(token in tokens for token in key_tokens):
            score = max(score, max(1, weight - 4))
    return score


def _column_tokens(column: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", column.lower()) if part]


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
