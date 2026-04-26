from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from src.scrapers.scheduler import start, stop

load_dotenv("config/.env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    start()
    yield
    stop()

app = FastAPI(lifespan=lifespan)