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


def run_eval(session: Session, settings: Settings, dataset: DatasetRecord, eval_path: Path, owner_hash: str | None = None) -> EvalRunResponse:
    cases = load_eval_cases(eval_path)
    results = []
    tool_hits = safety_hits = chart_hits = result_hits = 0
    for case in cases:
        response = answer_question(session, settings, dataset, case["question"])
        tools = [call["tool"] for call in response.tool_calls]
        expected_tools = case.get("expected_tools", [])
        tool_match = all(tool in tools for tool in expected_tools)
        safety_match = response.validation.get("blocked") == case.get("should_block", False)
        chart_match = bool(response.charts) == case.get("expects_chart", False)
        expected_columns = case.get("expected_columns", [])
        actual_columns = response.tables[-1]["columns"] if response.tables else []
        expected_min_rows = case.get("expected_min_rows")
        row_match = True if expected_min_rows is None else bool(response.tables and response.tables[-1]["row_count"] >= expected_min_rows)
        column_match = all(column in actual_columns for column in expected_columns)
        has_expected_result = case.get("expected_result") is not None
        value_match = _expected_result_matches(response.tables[-1] if response.tables else None, case.get("expected_result"))
        result_match = row_match and column_match
        tool_hits += int(tool_match)
        safety_hits += int(safety_match)
        chart_hits += int(chart_match)
        result_hits += int(result_match)
        scored_dimensions = [tool_match, safety_match, chart_match, result_match]
        if case.get("expected_result") is not None:
            scored_dimensions.append(value_match)
        judge_score = sum(scored_dimensions) / len(scored_dimensions)
        results.append({
            "id": case["id"],
            "question": case["question"],
            "tools": tools,
            "tool_match": tool_match,
            "safety_match": safety_match,
            "chart_match": chart_match,
            "result_match": result_match,
            "value_match": value_match,
            "value_scored": has_expected_result,
            "judge_score": judge_score,
        })
    total = max(1, len(cases))
    metrics = {
        "cases": len(cases),
        "tool_plan_accuracy": round(tool_hits / total, 4),
        "safety_accuracy": round(safety_hits / total, 4),
        "chart_expectation_accuracy": round(chart_hits / total, 4),
        "result_shape_accuracy": round(result_hits / total, 4),
        "value_accuracy": _value_accuracy(results),
        "mean_judge_score": round(sum(row["judge_score"] for row in results) / total, 4),
    }
    record = EvalRunRecord(
        id=str(uuid4()),
        owner_hash=owner_hash or dataset.owner_hash,
        status="completed",
        metrics_json=metrics,
        cases_json=results,
    )
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
        owner_hash="benchmark-owner",
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


def _expected_result_matches(table: dict | None, expected_result: dict | None) -> bool:
    if expected_result is None:
        return True
    if not table:
        return False
    rows = table.get("rows") or []
    expected_rows = expected_result.get("ordered_rows") or []
    if len(rows) < len(expected_rows):
        return False
    for index, expected_row in enumerate(expected_rows):
        actual = rows[index]
        for column, expected_value in expected_row.items():
            if actual.get(column) != expected_value:
                return False
    return True


def _value_accuracy(results: list[dict]) -> float | None:
    value_scored = [row for row in results if row.get("value_scored")]
    if not value_scored:
        return None
    return round(sum(row["value_match"] for row in value_scored) / len(value_scored), 4)
