from app.repositories import job_repository as repo
from app.schemas.job import JobStatus
from app.schemas.history import JobHistoryEntry, JobHistoryPage


def _duration_seconds(job: dict) -> float | None:
    started, finished = job.get("started_at"), job.get("completed_at")
    if started is None or finished is None:
        return None
    return round((finished - started).total_seconds(), 3)


def _to_entry(job: dict, stats: dict) -> JobHistoryEntry:
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
        total=stats.get("total", 0),
        completed=stats.get("completed", 0),
        failed=stats.get("failed", 0),
        pending_review=stats.get("pending_review", 0),
    )


def get_history(status: JobStatus | None, page: int, page_size: int) -> JobHistoryPage:
    offset = (page - 1) * page_size
    jobs, total = repo.list_jobs_page(status.value if status else None, page_size, offset)
    stats = repo.summarize_items([b["job_id"] for b in jobs]) if jobs else {}
    entries = [_to_entry(b, stats.get(b["job_id"], {})) for b in jobs]
    return JobHistoryPage(total=total, page=page, page_size=page_size, items=entries)