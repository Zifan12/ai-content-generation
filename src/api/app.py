"""
FastAPI app entry point.

Lifespan-managed APScheduler boots one job per active niche on startup and
shuts down cleanly on exit. Without lifespan binding, the scheduler either
leaks across reloads or never starts at all.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.scrapers.scheduler import start, stop


@asynccontextmanager
async def lifespan(app: FastAPI):
    start()
    yield
    stop()

app = FastAPI(lifespan=lifespan)