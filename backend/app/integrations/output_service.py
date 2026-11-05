import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class OutputService(Protocol):
    def deliver(self, job_id: str) -> None: ...


class MockOutputService:
    """Fake stand-in for Member 5's CSV, folder and API delivery. It only logs the request."""

    def deliver(self, job_id: str) -> None:
        logger.info("Delivery requested for job %s (mock)", job_id)


def get_output_service() -> OutputService:
    """THE swap point for Member 5's output delivery."""
    return MockOutputService()