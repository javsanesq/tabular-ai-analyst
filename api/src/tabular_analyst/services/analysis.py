from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from tabular_analyst.adapters.llm import build_planner
from tabular_analyst.core.config import Settings
from tabular_analyst.domain.models import AnalysisRecord, DatasetRecord
from tabular_analyst.domain.schemas import AnalysisResponse, ChartSpec, TransformSpec
from tabular_analyst.services.charts import build_chart
from tabular_analyst.services.files import read_dataframe
from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe
from tabular_analyst.services.sql_safety import run_safe_sql
from tabular_analyst.services.transforms import run_transform
from tabular_analyst.services.value_search import find_matching_values


def _dataset_path(settings: Settings, dataset: DatasetRecord) -> Path:
    return settings.upload_dir / dataset.stored_filename


def answer_question(session: Session, settings: Settings, dataset: DatasetRecord, question: str) -> AnalysisResponse:
    df = read_dataframe(_dataset_path(settings, dataset), settings)
    profile = dataset.profile_json or profile_dataframe(df)
    issues = dataset.issues_json or detect_quality_issues(df)
    if _profile_needs_refresh(profile):
        profile = profile_dataframe(df)
        dataset.profile_json = profile
        session.add(dataset)
        session.commit()
    planner = build_planner(settings)
    plan = planner.plan(question, profile, issues)
    tool_calls: list[dict] = []
    warnings: list[str] = []
    tables: list[dict] = []
    charts: list[dict] = []
    reasoning: list[dict] = []
    validation = {
        "sql_safety": "not_run",
        "chart_validation": "not_run",
        "transform_validation": "not_run",
        "blocked": False,
        "clarification_required": False,
        "tool_error": None,
    }
    trace = {"plan": plan, "executed_tools": []}

    if plan.get("blocked"):
        validation["blocked"] = True
        warnings.append(plan["reason"])
        answer = "I blocked this request because it asks for an unsafe or unsupported action. This copilot only runs validated read-only analysis tools."
    elif plan.get("clarification_required"):
        validation["clarification_required"] = True
        candidates = plan.get("candidate_columns", [])
        answer = plan.get("clarifying_question") or "I need one clarification before I can run the right analysis."
        if candidates:
            answer = f"{answer} Candidate columns: {', '.join(candidates)}."
    else:
        last_table_df: pd.DataFrame | None = None
        pending_value_matches: list[dict] = []
        answer_parts = []
        for assumption in plan.get("assumptions", []):
            answer_parts.append(f"Assumption: {assumption}")
            reasoning.append({"kind": "assumption", "label": assumption})
        for step in plan["steps"]:
            tool = step["tool"]
            args = dict(step.get("arguments", {}))
            record = {"tool": tool, "arguments": args, "status": "ok"}
            try:
                if tool == "profile_dataset":
                    record["result"] = {"row_count": profile["row_count"], "column_count": profile["column_count"]}
                elif tool == "detect_data_quality_issues":
                    record["result"] = {"issue_count": len(issues)}
                    if issues:
                        warnings.extend(issue["message"] for issue in issues[:5])
                elif tool == "run_safe_sql":
                    result = run_safe_sql(df, args["sql"])
                    validation["sql_safety"] = "passed"
                    tables.append({"name": "query_result", **result})
                    last_table_df = pd.DataFrame(result["rows"])
                    record["result"] = {"row_count": result["row_count"], "columns": result["columns"]}
                elif tool == "run_transform":
                    applied_match = _apply_value_search_filter(args, pending_value_matches)
                    if applied_match:
                        answer_parts.append(
                            f"Assumption: I matched '{applied_match['term']}' to {applied_match['column']} contains {applied_match['value']}."
                        )
                        reasoning.append({
                            "kind": "filter",
                            "label": f"{applied_match['column']} contains {applied_match['value']}",
                            "source": "value_search",
                        })
                        record["arguments"] = args
                    reasoning.extend(_reasoning_from_transform(args, profile))
                    result = run_transform(df, TransformSpec(**args))
                    validation["transform_validation"] = "passed"
                    tables.append({"name": "transform_result", **result})
                    last_table_df = pd.DataFrame(result["rows"])
                    record["result"] = {"row_count": result["row_count"], "columns": result["columns"]}
                elif tool == "find_matching_values":
                    result = find_matching_values(df, args.get("terms") or [], args.get("columns"), args.get("limit") or 5)
                    pending_value_matches = result["matches"]
                    record["result"] = result
                elif tool == "create_chart":
                    source = last_table_df if last_table_df is not None and not last_table_df.empty else df
                    chart = build_chart(source, ChartSpec(**args))
                    charts.append(chart)
                    validation["chart_validation"] = "passed"
                    record["result"] = {"chart_type": args["chart_type"], "validated": True}
                elif tool == "summarize_result":
                    answer_parts.append(f"Analyzed {profile['row_count']} rows and {profile['column_count']} columns using governed tools.")
                    if tables:
                        answer_parts.append(f"The main result returned {tables[-1]['row_count']} rows.")
                    if issues:
                        answer_parts.append(f"I found {len(issues)} data-quality warning(s); review the inspector before making decisions.")
                    if charts:
                        answer_parts.append("A validated Plotly chart was generated for the result.")
                    record["result"] = {"summary": "created"}
                else:
                    raise ValueError(f"Unsupported tool requested by planner: {tool}")
            except (HTTPException, KeyError, ValidationError, ValueError) as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                record["status"] = "error"
                record["error"] = detail
                validation["tool_error"] = {"tool": tool, "detail": detail}
                warnings.append(f"{tool} failed validation: {detail}")
                answer_parts.append("I could not complete the requested analysis because one governed tool failed validation. The failed tool call was saved in the trace.")
                tool_calls.append(record)
                trace["executed_tools"].append(record)
                break
            tool_calls.append(record)
            trace["executed_tools"].append(record)
        answer = " ".join(answer_parts) or "The dataset was profiled and no additional action was required."

    response_payload = {
        "answer": answer,
        "tables": tables,
        "charts": charts,
        "tool_calls": tool_calls,
        "warnings": warnings,
        "validation": validation,
        "trace": trace,
        "reasoning": _dedupe_reasoning(reasoning),
        "suggested_followups": _suggested_followups(plan),
    }
    analysis = AnalysisRecord(
        id=str(uuid4()),
        dataset_id=dataset.id,
        question=question,
        answer_json=response_payload,
        tool_calls_json=tool_calls,
        warnings_json=warnings,
        validation_json=validation,
        trace_json=trace,
    )
    session.add(analysis)
    session.commit()
    return AnalysisResponse(id=analysis.id, dataset_id=dataset.id, question=question, **response_payload)


def _apply_value_search_filter(args: dict, matches: list[dict]) -> dict | None:
    if not matches:
        return None
    filters = args.setdefault("filters", [])
    existing_columns = {filter_.get("column") for filter_ in filters if filter_.get("op") == "contains"}
    if existing_columns:
        return None
    selected = args.setdefault("select", [])
    for match in matches:
        column = match["column"]
        if column not in selected:
            selected.insert(max(0, len(selected) - 1), column)
        filters.append({"column": column, "op": "contains", "value": match["value"]})
        return match
    return None


def _reasoning_from_transform(args: dict, profile: dict) -> list[dict]:
    chips = []
    sort_by = args.get("sort_by")
    if sort_by:
        direction = "descending" if args.get("sort_desc", True) else "ascending"
        chips.append({"kind": "metric", "label": f"Metric: {sort_by}"})
        chips.append({"kind": "sort", "label": f"Sort: {direction}"})
    for filter_ in args.get("filters") or []:
        op = filter_.get("op")
        column = filter_.get("column")
        value = filter_.get("value")
        if op == "contains":
            chips.append({"kind": "filter", "label": f"Filter: {column} contains {value}"})
        elif op == "not_null":
            missing = _profile_missing_count(profile, column)
            label = f"Missing {column} excluded" if not missing else f"Missing {column} excluded ({missing} row(s))"
            chips.append({"kind": "caveat", "label": label})
        else:
            chips.append({"kind": "filter", "label": f"Filter: {column} {op} {value}"})
    return chips


def _profile_missing_count(profile: dict, column_name: str | None) -> int:
    for column in profile.get("columns", []):
        if column.get("name") == column_name:
            return int(column.get("missing_count") or 0)
    return 0


def _dedupe_reasoning(reasoning: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in reasoning:
        key = (item.get("kind"), item.get("label"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _suggested_followups(plan: dict) -> list[str]:
    if plan.get("clarification_required"):
        candidates = plan.get("candidate_columns", [])
        if candidates:
            return [f"Use {column} for this analysis." for column in candidates[:3]]
        return ["Tell me which column should define the metric.", "Show me the dataset profile first."]
    return [
        "Show the strongest data-quality risks.",
        "Create a chart for the most important numeric column.",
        "Compare averages across the main category.",
    ]


def _profile_needs_refresh(profile: dict) -> bool:
    return any(
        column.get("inferred_type") == "categorical" and "top_values" not in column
        for column in profile.get("columns", [])
    )
