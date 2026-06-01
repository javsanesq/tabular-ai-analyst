from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException, UploadFile, status

from tabular_analyst.core.config import Settings


SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


def validate_upload(file: UploadFile, settings: Settings) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV and XLSX files are supported.")
    content_type = file.content_type or "application/octet-stream"
    return content_type


def read_dataframe(path: Path, settings: Settings) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    if df.empty:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dataset is empty.")
    if len(df) > settings.max_rows:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Dataset has too many rows.")
    if len(df.columns) > settings.max_columns:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Dataset has too many columns.")
    df.columns = [str(col).strip() or f"column_{idx}" for idx, col in enumerate(df.columns)]
    return df


async def persist_upload(file: UploadFile, settings: Settings) -> tuple[str, Path, str]:
    content_type = validate_upload(file, settings)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower()
    dataset_id = str(uuid4())
    stored_path = settings.upload_dir / f"{dataset_id}{suffix}"
    size_limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    with stored_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > size_limit:
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds size limit.")
            out.write(chunk)
    return dataset_id, stored_path, content_type

