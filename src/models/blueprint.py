from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class BlueprintRecord(Base):
    """
    Versioned Blueprint storage — JSON payload per (content_item, extractor_version).
    """

    __tablename__ = "blueprints"
    __table_args__ = (
        UniqueConstraint(
            "content_item_id",
            "extractor_version", # Versioning stamp on Blueprint schema. Lets schema evolve without losing old data
            name="uniq_blueprint_content_extractor_version",
        ),
    ) 

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("raw_content_items.id"), index=True)
    extractor_version: Mapped[str] = mapped_column(String(20), index=True)
    extractor_model: Mapped[str] = mapped_column(String(100))
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confidence: Mapped[float] = mapped_column(Float)
    blueprint_data: Mapped[dict[str, Any]] = mapped_column(JSON) # Stored Blueprint Pydantic objects as JSON dict in SQLite/Postgres

