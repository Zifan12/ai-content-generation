from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from src.database import Base


class ViralVideo(Base):
    __tablename__ = "viral_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("raw_content_items.id"), unique=True, index=True, nullable=False)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id"), index=True, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(nullable=False)
    embed_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
