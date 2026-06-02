from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tabular_analyst.core.config import Settings, get_settings
from tabular_analyst.core.db import get_session
from tabular_analyst.core.security import AuthContext, require_demo_access
from tabular_analyst.domain.models import DatasetRecord, EvalRunRecord
from tabular_analyst.domain.schemas import EvalRunResponse
from tabular_analyst.services.evaluation import run_eval

router = APIRouter(prefix="/api/v1/evals")
EVAL_DATASET_DIR = Path("evals/datasets").resolve()
EVAL_FILE_ALLOWLIST = {
    "governed_analyst_eval": EVAL_DATASET_DIR / "governed_analyst_eval.jsonl",
    "governed_analyst_eval.jsonl": EVAL_DATASET_DIR / "governed_analyst_eval.jsonl",
    "evals/datasets/governed_analyst_eval.jsonl": EVAL_DATASET_DIR / "governed_analyst_eval.jsonl",
}


class EvalRequest(BaseModel):
    dataset_id: str
    eval_file: str = "evals/datasets/governed_analyst_eval.jsonl"


@router.post("/runs", response_model=EvalRunResponse)
def create_eval_run(
    payload: EvalRequest,
    auth: AuthContext = Depends(require_demo_access),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EvalRunResponse:
    dataset = session.get(DatasetRecord, payload.dataset_id)
    if not dataset or dataset.owner_hash != auth.owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    eval_path = EVAL_FILE_ALLOWLIST.get(payload.eval_file)
    if not eval_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Eval file must be a curated benchmark id.")
    eval_path = eval_path.resolve()
    if not eval_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval file not found.")
    return run_eval(session, settings, dataset, eval_path, owner_hash=auth.owner_hash)


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
def get_eval_run(
    run_id: str,
    auth: AuthContext = Depends(require_demo_access),
    session: Session = Depends(get_session),
) -> EvalRunResponse:
    record = session.get(EvalRunRecord, run_id)
    if not record or record.owner_hash != auth.owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found.")
    return EvalRunResponse(id=record.id, status=record.status, metrics=record.metrics_json, cases=record.cases_json)
