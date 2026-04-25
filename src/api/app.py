from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.scrapers.scheduler import start, stop

@asynccontextmanager
async def lifespan(app: FastAPI):
    start()
    yield
    stop()

app = FastAPI(lifespan=lifespan)