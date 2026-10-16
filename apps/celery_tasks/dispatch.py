"""Only trusted application code may enqueue Celery tasks."""

from django.db import transaction


def send_after_commit(task, *args, **kwargs) -> None:
    """Publish after DB commit; publishing failure requires an application outbox.

    kwargs are passed to apply_async as task keyword arguments, not Celery options.
    """
    transaction.on_commit(lambda: task.apply_async(args=args, kwargs=kwargs))
