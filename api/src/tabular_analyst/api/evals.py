from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tabular_analyst.core.config import Settings, get_settings
from tabular_analyst.core.db import get_session
from tabular_analyst.core.security import require_demo_access
from tabular_analyst.domain.models import DatasetRecord, EvalRunRecord
from tabular_analyst.domain.schemas import EvalRunResponse
from tabular_analyst.services.evaluation import run_eval

router = APIRouter(prefix="/api/v1/evals", dependencies=[Depends(require_demo_access)])


class EvalRequest(BaseModel):
    dataset_id: str
    eval_file: str = "evals/datasets/governed_analyst_eval.jsonl"


@router.post("/runs", response_model=EvalRunResponse)
def create_eval_run(payload: EvalRequest, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> EvalRunResponse:
    dataset = session.get(DatasetRecord, payload.dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    eval_path = Path(payload.eval_file)
    if not eval_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval file not found.")
    return run_eval(session, settings, dataset, eval_path)


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
def get_eval_run(run_id: str, session: Session = Depends(get_session)) -> EvalRunResponse:
    record = session.get(EvalRunRecord, run_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found.")
    return EvalRunResponse(id=record.id, status=record.status, metrics=record.metrics_json, cases=record.cases_json)

