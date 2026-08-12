"""Research logging — NOT IMPLEMENTED (Stage 8).

Boundary for the structured event/session logs used by research and baseline
comparison. Left unimplemented so we don't ship fake metrics.
"""


def log_event(*args, **kwargs):
    raise NotImplementedError("Research logging is implemented in Stage 8")
