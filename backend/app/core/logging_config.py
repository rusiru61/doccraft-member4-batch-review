import logging
from contextvars import ContextVar

# Holds the current request's ID. "-" means "not inside a request" (startup, worker).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Copies the current request ID onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    for existing in list(root.handlers):  # makes this safe to call more than once
        if getattr(existing, "_doccraft", False):
            root.removeHandler(existing)

    handler = logging.StreamHandler()
    handler._doccraft = True
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)