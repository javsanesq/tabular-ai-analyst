from pathlib import Path

from tabular_analyst.core.config import get_settings
from tabular_analyst.core.migrations import run_migrations
from tabular_analyst.core.db import SessionLocal
from tabular_analyst.services.evaluation import create_dataset_from_sample, run_eval


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    sample = Path("samples/wine_quality_subset.csv")
    eval_file = Path("evals/datasets/governed_analyst_eval.jsonl")
    with SessionLocal() as session:
        dataset = create_dataset_from_sample(session, settings, sample)
        result = run_eval(session, settings, dataset, eval_file)
    report = Path("docs/benchmark-report.md")
    report.write_text(
        "# Tabular Analyst Benchmark Report\n\n"
        "This benchmark evaluates governed tool selection, unsafe-request blocking, chart expectation matching, and deterministic judge scoring.\n\n"
        "## Configuration\n\n"
        f"- Dataset: `{sample}`\n"
        f"- Eval file: `{eval_file}`\n"
        f"- Cases: {result.metrics['cases']}\n"
        "- Planner: deterministic governed planner for reproducible CI\n\n"
        "## Results\n\n"
        "| Metric | Value |\n| --- | ---: |\n"
        f"| Tool plan accuracy | {result.metrics['tool_plan_accuracy']:.4f} |\n"
        f"| Safety accuracy | {result.metrics['safety_accuracy']:.4f} |\n"
        f"| Chart expectation accuracy | {result.metrics['chart_expectation_accuracy']:.4f} |\n"
        f"| Mean judge score | {result.metrics['mean_judge_score']:.4f} |\n\n"
        "## Per-Case Results\n\n"
        "| ID | Tools | Tool Match | Safety Match | Chart Match | Judge |\n| --- | --- | ---: | ---: | ---: | ---: |\n"
        + "\n".join(
            f"| {case['id']} | {', '.join(case['tools']) or 'BLOCKED'} | {case['tool_match']} | {case['safety_match']} | {case['chart_match']} | {case['judge_score']:.2f} |"
            for case in result.cases
        )
        + "\n\n## Interpretation\n\n"
        "The benchmark is intentionally small but covers the failure modes that make this project different from a generic chatbot: bounded tools, SQL safety, chart validation, and refusal of unsafe requests.\n",
        encoding="utf-8",
    )
    print(report.read_text())


if __name__ == "__main__":
    main()

