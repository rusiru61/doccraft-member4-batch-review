from app.repositories import job_repository as repo
from app.schemas.history import JobHistoryEntry, JobHistoryPage
from app.schemas.job import JobStatus


def _duration_seconds(job: dict) -> float | None:
    """Processing time only: from the worker starting to the worker finishing."""
    started, processed = job.get("started_at"), job.get("processed_at")
    if started is None or processed is None:
        return None
    return round((processed - started).total_seconds(), 3)


def _to_entry(job: dict, stats: dict) -> JobHistoryEntry:
    total = stats.get("total", 0)
    completed, failed = stats.get("completed", 0), stats.get("failed", 0)
    percent = round((completed + failed) / total * 100, 1) if total else 0.0
    return JobHistoryEntry(
        job_id=job["job_id"],
        name=job["name"],
        priority=job["priority"],
        status=job["status"],
        created_by=job.get("created_by"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        duration_seconds=_duration_seconds(job),
        total=total,
        completed=completed,
        failed=failed,
        pending_review=stats.get("pending_review", 0),
        percent_complete=percent,
    )


def get_history(status: JobStatus | None, page: int, page_size: int) -> JobHistoryPage:
    offset = (page - 1) * page_size
    jobs, total = repo.list_jobs_page(status.value if status else None, page_size, offset)
    stats = repo.summarize_items([j["job_id"] for j in jobs]) if jobs else {}
    entries = [_to_entry(j, stats.get(j["job_id"], {})) for j in jobs]
    return JobHistoryPage(total=total, page=page, page_size=page_size, items=entries)