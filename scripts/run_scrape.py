import asyncio
import os
from pathlib import Path
from typing import Any

import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from src.database import DB_PATH, SessionLocal
from src.models.niche import Niche
from src.models.trend import RawContentItem
from src.scrapers.youtube import YoutubeScraperSessionLocal, engine, Base
from src.models.niche import Niche
from src.scrapers.youtube import YoutubeScraper

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
DATA_DIR = PROJECT_ROOT / "data"


def run_migrations():
    