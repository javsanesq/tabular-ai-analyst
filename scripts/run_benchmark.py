from pathlib import Path

from tabular_analyst.core.config import get_settings
from tabular_analyst.core.migrations import run_migrations
from tabular_analyst.core.db import SessionLocal
from tabular_analyst.services.evaluation import create_dataset_from_sample, run_eval


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    suites = [
        (Path("samples/wine_quality_subset.csv"), Path("evals/datasets/governed_analyst_eval.jsonl")),
        (Path("samples/video_games_subset.csv"), Path("evals/datasets/video_games_semantic_eval.jsonl")),
    ]
    results = []
    with SessionLocal() as session:
        for sample, eval_file in suites:
            dataset = create_dataset_from_sample(session, settings, sample)
            results.append((sample, eval_file, run_eval(session, settings, dataset, eval_file)))
    aggregate = _aggregate_metrics([result for _, _, result in results])
    report = Path("docs/benchmark-report.md")
    report.write_text(
        "# Tabular Analyst Benchmark Report\n\n"
        "This benchmark evaluates governed tool conformance, unsafe-request blocking, chart expectation matching, result-shape checks, and expected-value correctness for curated cases.\n\n"
        "## Configuration\n\n"
        + "\n".join(f"- Suite: `{sample}` with `{eval_file}` ({result.metrics['cases']} cases)" for sample, eval_file, result in results)
        + "\n"
        f"- Total cases: {aggregate['cases']}\n"
        "- Planner: deterministic governed planner for reproducible CI\n\n"
        "## Results\n\n"
        "| Metric | Value |\n| --- | ---: |\n"
        f"| Tool plan accuracy | {aggregate['tool_plan_accuracy']:.4f} |\n"
        f"| Safety accuracy | {aggregate['safety_accuracy']:.4f} |\n"
        f"| Chart expectation accuracy | {aggregate['chart_expectation_accuracy']:.4f} |\n"
        f"| Result shape accuracy | {aggregate['result_shape_accuracy']:.4f} |\n"
        f"| Expected-value accuracy | {aggregate['value_accuracy']:.4f} |\n"
        f"| Mean conformance score | {aggregate['mean_judge_score']:.4f} |\n\n"
        "## Per-Case Results\n\n"
        "| Suite | ID | Tools | Tool Match | Safety Match | Chart Match | Result Match | Value Match | Score |\n| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        + "\n".join(
            f"| {sample.stem} | {case['id']} | {', '.join(case['tools']) or 'BLOCKED'} | {case['tool_match']} | {case['safety_match']} | {case['chart_match']} | {case['result_match']} | {_format_value_match(case)} | {case['judge_score']:.2f} |"
            for sample, _, result in results
            for case in result.cases
        )
        + "\n\n## Interpretation\n\n"
        "This is a deterministic conformance and regression benchmark, not a claim of broad analyst quality. It now includes expected-value assertions for ranking and filtered-ranking cases so wrong sort direction, wrong metric selection, or ignored filters can fail CI. The next evaluation upgrade is a larger public suite plus qualitative LLM-judge scoring with real OpenAI credentials.\n",
        encoding="utf-8",
    )
    print(report.read_text())


def _aggregate_metrics(results) -> dict[str, float]:
    cases = [case for result in results for case in result.cases]
    total = max(1, len(cases))
    return {
        "cases": len(cases),
        "tool_plan_accuracy": sum(case["tool_match"] for case in cases) / total,
        "safety_accuracy": sum(case["safety_match"] for case in cases) / total,
        "chart_expectation_accuracy": sum(case["chart_match"] for case in cases) / total,
        "result_shape_accuracy": sum(case["result_match"] for case in cases) / total,
        "value_accuracy": _aggregate_value_accuracy(cases),
        "mean_judge_score": sum(case["judge_score"] for case in cases) / total,
    }


def _aggregate_value_accuracy(cases: list[dict]) -> float:
    scored = [case for case in cases if case.get("value_scored")]
    if not scored:
        return 0.0
    return sum(case["value_match"] for case in scored) / len(scored)


def _format_value_match(case: dict) -> str:
    if not case.get("value_scored"):
        return "N/A"
    return str(case["value_match"])


if __name__ == "__main__":
    main()
