from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from tabular_analyst.adapters.llm import build_planner
from tabular_analyst.core.config import Settings
from tabular_analyst.domain.models import AnalysisRecord, DatasetRecord
from tabular_analyst.domain.schemas import AnalysisResponse, ChartSpec
from tabular_analyst.services.charts import build_chart
from tabular_analyst.services.files import read_dataframe
from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe
from tabular_analyst.services.sql_safety import run_safe_sql


def _dataset_path(settings: Settings, dataset: DatasetRecord) -> Path:
    return settings.upload_dir / dataset.stored_filename


def answer_question(session: Session, settings: Settings, dataset: DatasetRecord, question: str) -> AnalysisResponse:
    df = read_dataframe(_dataset_path(settings, dataset), settings)
    profile = dataset.profile_json or profile_dataframe(df)
    issues = dataset.issues_json or detect_quality_issues(df)
    planner = build_planner(settings)
    plan = planner.plan(question, profile, issues)
    tool_calls: list[dict] = []
    warnings: list[str] = []
    tables: list[dict] = []
    charts: list[dict] = []
    validation = {"sql_safety": "not_run", "chart_validation": "not_run", "blocked": False}
    trace = {"plan": plan, "executed_tools": []}

    if plan.get("blocked"):
        validation["blocked"] = True
        warnings.append(plan["reason"])
        answer = "I blocked this request because it asks for an unsafe or unsupported action. This copilot only runs validated read-only analysis tools."
    else:
        last_table_df: pd.DataFrame | None = None
        answer_parts = []
        for step in plan["steps"]:
            tool = step["tool"]
            args = step.get("arguments", {})
            record = {"tool": tool, "arguments": args, "status": "ok"}
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
            elif tool == "create_chart":
                source = last_table_df if last_table_df is not None and not last_table_df.empty else df
                chart = build_chart(source, ChartSpec(**args))
                charts.append(chart)
                validation["chart_validation"] = "passed"
                record["result"] = {"chart_type": args["chart_type"], "validated": True}
            elif tool == "summarize_result":
                answer_parts.append(f"Analyzed {profile['row_count']} rows and {profile['column_count']} columns using governed tools.")
                if tables:
                    answer_parts.append(f"The main query returned {tables[-1]['row_count']} rows.")
                if issues:
                    answer_parts.append(f"I found {len(issues)} data-quality warning(s); review the inspector before making decisions.")
                if charts:
                    answer_parts.append("A validated Plotly chart was generated for the result.")
                record["result"] = {"summary": "created"}
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
        "suggested_followups": [
            "Show the strongest data-quality risks.",
            "Create a chart for the most important numeric column.",
            "Compare averages across the main category.",
        ],
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

