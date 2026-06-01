import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from tabular_analyst.core.config import Settings
from tabular_analyst.domain.models import DatasetRecord, EvalRunRecord
from tabular_analyst.domain.schemas import EvalRunResponse
from tabular_analyst.services.analysis import answer_question
from tabular_analyst.services.files import read_dataframe
from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe


def load_eval_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_eval(session: Session, settings: Settings, dataset: DatasetRecord, eval_path: Path) -> EvalRunResponse:
    cases = load_eval_cases(eval_path)
    results = []
    tool_hits = safety_hits = chart_hits = 0
    for case in cases:
        response = answer_question(session, settings, dataset, case["question"])
        tools = [call["tool"] for call in response.tool_calls]
        expected_tools = case.get("expected_tools", [])
        tool_match = all(tool in tools for tool in expected_tools)
        safety_match = response.validation.get("blocked") == case.get("should_block", False)
        chart_match = bool(response.charts) == case.get("expects_chart", False)
        tool_hits += int(tool_match)
        safety_hits += int(safety_match)
        chart_hits += int(chart_match)
        results.append({
            "id": case["id"],
            "question": case["question"],
            "tools": tools,
            "tool_match": tool_match,
            "safety_match": safety_match,
            "chart_match": chart_match,
            "judge_score": 1.0 if tool_match and safety_match and chart_match else 0.5,
        })
    total = max(1, len(cases))
    metrics = {
        "cases": len(cases),
        "tool_plan_accuracy": round(tool_hits / total, 4),
        "safety_accuracy": round(safety_hits / total, 4),
        "chart_expectation_accuracy": round(chart_hits / total, 4),
        "mean_judge_score": round(sum(row["judge_score"] for row in results) / total, 4),
    }
    record = EvalRunRecord(id=str(uuid4()), status="completed", metrics_json=metrics, cases_json=results)
    session.add(record)
    session.commit()
    return EvalRunResponse(id=record.id, status=record.status, metrics=metrics, cases=results)


def create_dataset_from_sample(session: Session, settings: Settings, sample_path: Path) -> DatasetRecord:
    df = read_dataframe(sample_path, settings)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = str(uuid4())
    stored = settings.upload_dir / f"{dataset_id}{sample_path.suffix}"
    stored.write_bytes(sample_path.read_bytes())
    profile = profile_dataframe(df)
    issues = detect_quality_issues(df)
    record = DatasetRecord(
        id=dataset_id,
        stored_filename=stored.name,
        original_filename=sample_path.name,
        content_type="text/csv",
        row_count=len(df),
        column_count=len(df.columns),
        profile_json=profile,
        issues_json=issues,
    )
    session.add(record)
    session.commit()
    return record

