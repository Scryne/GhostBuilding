from celery import Celery
from app.config import settings

celery_app = Celery(
    "ghostbuilding_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.task_routes = {
    "app.worker.*": "main-queue"
}

@celery_app.task
def sample_task(task_name: str):
    return f"Task {task_name} processed"
