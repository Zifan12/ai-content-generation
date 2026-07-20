"""
FastAPI app entry point.

Currently a bare app with no routes. It previously existed only to host an
APScheduler lifespan that booted one recurring scrape job per active niche;
that scheduler went with the corpus lane (ADR-0009), and no HTTP surface has
replaced it — the pipeline is driven entirely by the operator scripts under
``scripts/``. Kept as the mount point for a future dashboard/control API.
"""

from fastapi import FastAPI

app = FastAPI()
