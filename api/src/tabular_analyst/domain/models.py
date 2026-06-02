from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DatasetRecord(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True, default="legacy-demo")
    stored_filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    profile_json: Mapped[dict] = mapped_column(JSON)
    issues_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analyses: Mapped[list["AnalysisRecord"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True, default="legacy-demo")
    question: Mapped[str] = mapped_column(Text)
    answer_json: Mapped[dict] = mapped_column(JSON)
    tool_calls_json: Mapped[list] = mapped_column(JSON)
    warnings_json: Mapped[list] = mapped_column(JSON)
    validation_json: Mapped[dict] = mapped_column(JSON)
    trace_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped[DatasetRecord] = relationship(back_populates="analyses")


class EvalRunRecord(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True, default="legacy-demo")
    status: Mapped[str] = mapped_column(String(40))
    metrics_json: Mapped[dict] = mapped_column(JSON)
    cases_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoQuotaRecord(Base):
    __tablename__ = "demo_quota_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
