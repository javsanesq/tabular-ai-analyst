from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    id: str
    original_filename: str
    row_count: int
    column_count: int
    created_at: str


class DatasetDetail(DatasetSummary):
    profile: dict[str, Any]
    issues: list[dict[str, Any]]


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "scatter", "histogram", "box", "heatmap"]
    x: str | None = None
    y: str | None = None
    color: str | None = None
    title: str
    dataframe_ref: str = "result"


class TransformSpec(BaseModel):
    select: list[str] | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: dict[str, Literal["sum", "mean", "median", "min", "max", "count"]] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_desc: bool = True
    limit: int = Field(default=100, ge=1, le=500)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class AnalysisResponse(BaseModel):
    id: str
    dataset_id: str
    question: str
    answer: str
    tables: list[dict[str, Any]]
    charts: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    warnings: list[str]
    validation: dict[str, Any]
    trace: dict[str, Any]
    reasoning: list[dict[str, Any]] = Field(default_factory=list)
    suggested_followups: list[str]


class EvalRunResponse(BaseModel):
    id: str
    status: str
    metrics: dict[str, Any]
    cases: list[dict[str, Any]]
