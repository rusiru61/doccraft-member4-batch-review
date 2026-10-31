from celery import Celery
from kombu import Queue

from app.core.config import settings

# Names sort alphabetically in priority order, which the Redis "sorted" strategy relies on.
_QUEUE_BY_PRIORITY = {"high": "p1_high", "medium": "p2_medium", "low": "p3_low"}
PRIORITY_QUEUES = tuple(_QUEUE_BY_PRIORITY.values())


def queue_for_priority(priority: str) -> str:
    return _QUEUE_BY_PRIORITY.get(priority, "p2_medium")


celery_app = Celery(
    "doccraft_member4",
    broker=settings.redis_url,
    include=["app.tasks.processing_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,          # MongoDB is the source of truth
    task_acks_late=True,              # acknowledge only after the task finishes
    worker_prefetch_multiplier=1,     # one message at a time
    broker_connection_retry_on_startup=True,
    task_publish_retry_policy={       # fail fast when Redis is down
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.5,
    },
    timezone="UTC",
    task_queues=tuple(Queue(name) for name in PRIORITY_QUEUES),
    task_default_queue="p2_medium",
    broker_transport_options={"queue_order_strategy": "sorted"},
)