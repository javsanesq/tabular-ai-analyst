from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tabular_analyst.core.db import get_session
from tabular_analyst.core.security import require_demo_access
from tabular_analyst.domain.models import AnalysisRecord

router = APIRouter(prefix="/api/v1/analyses", dependencies=[Depends(require_demo_access)])


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str, session: Session = Depends(get_session)) -> dict:
    record = session.get(AnalysisRecord, analysis_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return {"id": record.id, "dataset_id": record.dataset_id, "question": record.question, **record.answer_json}

