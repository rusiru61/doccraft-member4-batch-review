from fastapi import FastAPI

from app.api import batches, health, review, results
from app.core.config import settings

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title=settings.app_name)
app.include_router(health.router)
app.include_router(batches.router)
app.include_router(review.router)
app.include_router(results.router)