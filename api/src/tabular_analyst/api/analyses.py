from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from tabular_analyst.core.db import get_session
from tabular_analyst.core.security import AuthContext, require_demo_access
from tabular_analyst.domain.models import AnalysisRecord

router = APIRouter(prefix="/api/v1/analyses")


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: str,
    auth: AuthContext = Depends(require_demo_access),
    session: Session = Depends(get_session),
) -> dict:
    record = session.get(AnalysisRecord, analysis_id)
    if not record or record.owner_hash != auth.owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return {"id": record.id, "dataset_id": record.dataset_id, "question": record.question, **record.answer_json}
