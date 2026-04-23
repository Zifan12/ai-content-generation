from sqlalchemy import Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hashtag_seeds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)