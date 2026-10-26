from app.repositories import batch_repository as repo
from app.schemas.batch import BatchStatus
from app.schemas.history import JobHistoryEntry, JobHistoryPage


def _duration_seconds(batch: dict) -> float | None:
    started, finished = batch.get("started_at"), batch.get("completed_at")
    if started is None or finished is None:
        return None
    return round((finished - started).total_seconds(), 3)


def _to_entry(batch: dict, stats: dict) -> JobHistoryEntry:
    return JobHistoryEntry(
        batch_id=batch["batch_id"],
        name=batch["name"],
        priority=batch["priority"],
        status=batch["status"],
        created_by=batch.get("created_by"),
        created_at=batch["created_at"],
        started_at=batch.get("started_at"),
        completed_at=batch.get("completed_at"),
        duration_seconds=_duration_seconds(batch),
        total=stats.get("total", 0),
        completed=stats.get("completed", 0),
        failed=stats.get("failed", 0),
        pending_review=stats.get("pending_review", 0),
    )


def get_history(status: BatchStatus | None, limit: int, offset: int) -> JobHistoryPage:
    batches, total = repo.list_batches_page(status.value if status else None, limit, offset)
    stats = repo.summarize_items([b["batch_id"] for b in batches]) if batches else {}
    entries = [_to_entry(b, stats.get(b["batch_id"], {})) for b in batches]
    return JobHistoryPage(total=total, limit=limit, offset=offset, items=entries)