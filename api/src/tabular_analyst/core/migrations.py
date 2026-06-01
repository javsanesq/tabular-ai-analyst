from alembic import command
from alembic.config import Config
from pathlib import Path

from tabular_analyst.core.config import get_settings


def run_migrations() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite") and settings.app_env == "test":
        from tabular_analyst.core.db import engine
        from tabular_analyst.domain.models import Base

        Base.metadata.create_all(engine)
        return
    api_dir = Path(__file__).resolve().parents[3]
    alembic_cfg = Config(str(api_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_dir / "alembic"))
    command.upgrade(alembic_cfg, "head")
