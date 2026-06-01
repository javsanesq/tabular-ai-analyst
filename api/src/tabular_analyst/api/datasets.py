from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tabular_analyst.core.config import Settings, get_settings
from tabular_analyst.core.db import get_session
from tabular_analyst.core.security import require_demo_access
from tabular_analyst.domain.models import AnalysisRecord, DatasetRecord
from tabular_analyst.domain.schemas import AnalysisResponse, DatasetDetail, DatasetSummary, QuestionRequest
from tabular_analyst.services.analysis import answer_question
from tabular_analyst.services.files import persist_upload, read_dataframe
from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe

router = APIRouter(prefix="/api/v1/datasets", dependencies=[Depends(require_demo_access)])


def _summary(record: DatasetRecord) -> DatasetSummary:
    return DatasetSummary(
        id=record.id,
        original_filename=record.original_filename,
        row_count=record.row_count,
        column_count=record.column_count,
        created_at=record.created_at.isoformat(),
    )


@router.post("/upload", response_model=DatasetDetail)
async def upload_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DatasetDetail:
    dataset_id, stored_path, content_type = await persist_upload(file, settings)
    df = read_dataframe(stored_path, settings)
    profile = profile_dataframe(df)
    issues = detect_quality_issues(df)
    record = DatasetRecord(
        id=dataset_id,
        stored_filename=stored_path.name,
        original_filename=file.filename or stored_path.name,
        content_type=content_type,
        row_count=len(df),
        column_count=len(df.columns),
        profile_json=profile,
        issues_json=issues,
    )
    session.add(record)
    session.commit()
    return DatasetDetail(**_summary(record).model_dump(), profile=profile, issues=issues)


@router.get("", response_model=list[DatasetSummary])
def list_datasets(session: Session = Depends(get_session)) -> list[DatasetSummary]:
    records = session.scalars(select(DatasetRecord).order_by(DatasetRecord.created_at.desc())).all()
    return [_summary(record) for record in records]


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> DatasetDetail:
    record = session.get(DatasetRecord, dataset_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return DatasetDetail(**_summary(record).model_dump(), profile=record.profile_json, issues=record.issues_json)


@router.get("/{dataset_id}/profile")
def get_profile(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    record = session.get(DatasetRecord, dataset_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return {"profile": record.profile_json, "issues": record.issues_json}


@router.post("/{dataset_id}/questions", response_model=AnalysisResponse)
def ask_question(
    dataset_id: str,
    payload: QuestionRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    record = session.get(DatasetRecord, dataset_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return answer_question(session, settings, record, payload.question)


@router.get("/{dataset_id}/analyses")
def list_analyses(dataset_id: str, session: Session = Depends(get_session)) -> list[dict]:
    records = session.scalars(select(AnalysisRecord).where(AnalysisRecord.dataset_id == dataset_id).order_by(AnalysisRecord.created_at.desc())).all()
    return [{"id": row.id, "question": row.question, "created_at": row.created_at.isoformat(), **row.answer_json} for row in records]

