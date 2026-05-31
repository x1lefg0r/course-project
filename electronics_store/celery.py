import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "electronics_store.settings")

app = Celery("electronics_store")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Диагностическая задача для проверки работы Celery."""
    print(f"Request: {self.request!r}")
