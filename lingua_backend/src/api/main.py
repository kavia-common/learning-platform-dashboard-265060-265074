from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api import repo
from src.api.models import (
    AnalyticsEventIn,
    AnalyticsEventOut,
    AnalyticsSummaryOut,
    AttemptCreateIn,
    AttemptOut,
    LessonOut,
    NotificationMarkReadIn,
    NotificationOut,
    NotificationSettingsOut,
    NotificationSettingsUpdateIn,
    PagedResponse,
    ProgressOut,
    ProgressUpsertIn,
    UserOut,
)
from src.db.session import check_db_connection, db_session

openapi_tags = [
    {"name": "Health", "description": "Service and dependency health checks."},
    {"name": "Lessons", "description": "Lesson catalog endpoints."},
    {"name": "Exercises", "description": "Exercise catalog and attempts."},
    {"name": "Progress", "description": "User progress tracking."},
    {"name": "Notifications", "description": "In-app notifications and preferences."},
    {"name": "Analytics", "description": "Analytics events and summaries."},
    {"name": "Admin", "description": "Admin endpoints (MVP: no auth enforced)."},
]

app = FastAPI(
    title="Lingua Backend API",
    description=(
        "FastAPI monolith for the Lingua learning dashboard. "
        "Provides lesson/exercise content, progress tracking, notifications, and analytics."
    ),
    version="0.2.0",
    openapi_tags=openapi_tags,
)

# NOTE: For MVP/demo we allow all origins. In production, restrict to frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Session:
    """FastAPI dependency that provides a DB session per request."""
    with db_session() as s:
        yield s


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_request: Request, exc: SQLAlchemyError):
    """Return a consistent payload for database errors."""
    # Avoid leaking sensitive DB details to clients.
    return JSONResponse(
        status_code=500,
        content={"message": "Database error", "detail": str(exc.__class__.__name__)},
    )


@app.exception_handler(RuntimeError)
async def runtime_exception_handler(_request: Request, exc: RuntimeError):
    """Return a consistent payload for runtime configuration errors."""
    return JSONResponse(
        status_code=500,
        content={"message": "Server configuration error", "detail": str(exc)},
    )


@app.get(
    "/",
    tags=["Health"],
    summary="Health check",
    description="Basic health check endpoint used by the frontend to verify connectivity.",
)
# PUBLIC_INTERFACE
def health_check():
    """Health check endpoint.

    Returns:
      A simple empty JSON object (frontend expects JSON).
    """
    return {}


@app.get(
    "/health/db",
    tags=["Health"],
    summary="Database health check",
    description="Verifies the backend can connect to Postgres using DATABASE_URL.",
)
# PUBLIC_INTERFACE
def health_check_db():
    """Database health check.

    Returns:
      {\"message\": \"OK\"} if SELECT 1 succeeds.
    """
    check_db_connection()
    return {"message": "OK"}


@app.get(
    "/lessons",
    tags=["Lessons"],
    summary="List lessons",
    description="List lessons with optional filters (language, level) and pagination.",
    response_model=PagedResponse,
)
# PUBLIC_INTERFACE
def list_lessons(
    language: Optional[str] = Query(None, description="Filter by language code"),
    level: Optional[str] = Query(None, description="Filter by level"),
    published_only: bool = Query(True, description="Only return published lessons"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset"),
    db: Session = Depends(get_db),
):
    """List lessons."""
    data = repo.list_lessons(db, language, level, published_only, limit, offset)
    return {
        "items": [LessonOut(**x).model_dump() for x in data["items"]],
        "total": data["total"],
        "limit": limit,
        "offset": offset,
    }


@app.get(
    "/lessons/{lesson_id}",
    tags=["Lessons"],
    summary="Get lesson by id",
    description="Fetch a single lesson by UUID.",
    response_model=LessonOut,
)
# PUBLIC_INTERFACE
def get_lesson(lesson_id: UUID, db: Session = Depends(get_db)):
    """Get a lesson."""
    return LessonOut(**repo.get_lesson(db, lesson_id))


@app.get(
    "/lessons/{lesson_id}/exercises",
    tags=["Exercises"],
    summary="List exercises for a lesson",
    description="Returns exercises for a given lesson id.",
)
# PUBLIC_INTERFACE
def list_exercises_for_lesson(lesson_id: UUID, db: Session = Depends(get_db)):
    """List exercises for a lesson."""
    items = repo.list_exercises_for_lesson(db, lesson_id)
    return [x for x in items]


@app.post(
    "/attempts",
    tags=["Exercises"],
    summary="Create an exercise attempt",
    description=(
        "Creates an exercise attempt and performs MVP grading when possible. "
        "Answer payload is flexible JSON."
    ),
    response_model=AttemptOut,
)
# PUBLIC_INTERFACE
def create_attempt(payload: AttemptCreateIn, db: Session = Depends(get_db)):
    """Create an exercise attempt."""
    attempt = repo.create_attempt(
        db=db,
        user_id=payload.user_id,
        exercise_id=payload.exercise_id,
        answer=payload.answer,
    )
    return AttemptOut(**attempt)


@app.get(
    "/users/{user_id}/progress",
    tags=["Progress"],
    summary="Get user progress",
    description="Returns per-lesson progress records for the given user.",
    response_model=list[ProgressOut],
)
# PUBLIC_INTERFACE
def get_user_progress(user_id: UUID, db: Session = Depends(get_db)):
    """Get user progress."""
    return [ProgressOut(**x) for x in repo.get_progress(db, user_id)]


@app.put(
    "/users/{user_id}/lessons/{lesson_id}/progress",
    tags=["Progress"],
    summary="Upsert lesson progress",
    description="Upserts a user's lesson progress_pct (0..100).",
    response_model=ProgressOut,
)
# PUBLIC_INTERFACE
def upsert_user_lesson_progress(
    user_id: UUID, lesson_id: UUID, payload: ProgressUpsertIn, db: Session = Depends(get_db)
):
    """Upsert user lesson progress."""
    return ProgressOut(**repo.upsert_progress(db, user_id, lesson_id, payload.progress_pct))


@app.get(
    "/users/{user_id}/notifications",
    tags=["Notifications"],
    summary="List user notifications",
    description="List in-app notifications for a user with pagination.",
    response_model=PagedResponse,
)
# PUBLIC_INTERFACE
def list_user_notifications(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset"),
    db: Session = Depends(get_db),
):
    """List notifications."""
    data = repo.list_notifications(db, user_id, limit, offset)
    return {
        "items": [NotificationOut(**x).model_dump() for x in data["items"]],
        "total": data["total"],
        "limit": limit,
        "offset": offset,
    }


@app.patch(
    "/users/{user_id}/notifications/{notification_id}",
    tags=["Notifications"],
    summary="Mark notification read/unread",
    description="Updates read state for a notification.",
    response_model=NotificationOut,
)
# PUBLIC_INTERFACE
def mark_notification(
    user_id: UUID, notification_id: UUID, payload: NotificationMarkReadIn, db: Session = Depends(get_db)
):
    """Mark a notification read/unread."""
    return NotificationOut(**repo.mark_notification_read(db, user_id, notification_id, payload.is_read))


@app.get(
    "/users/{user_id}/notification-settings",
    tags=["Notifications"],
    summary="Get notification settings",
    description="Returns notification settings; creates defaults if missing.",
    response_model=NotificationSettingsOut,
)
# PUBLIC_INTERFACE
def get_notification_settings(user_id: UUID, db: Session = Depends(get_db)):
    """Get notification settings."""
    return NotificationSettingsOut(**repo.get_notification_settings(db, user_id))


@app.patch(
    "/users/{user_id}/notification-settings",
    tags=["Notifications"],
    summary="Update notification settings",
    description="Partially updates notification settings fields.",
    response_model=NotificationSettingsOut,
)
# PUBLIC_INTERFACE
def patch_notification_settings(
    user_id: UUID, payload: NotificationSettingsUpdateIn, db: Session = Depends(get_db)
):
    """Update notification settings."""
    updated = repo.update_notification_settings(db, user_id, payload.model_dump())
    return NotificationSettingsOut(**updated)


@app.post(
    "/analytics/events",
    tags=["Analytics"],
    summary="Ingest an analytics event",
    description="Inserts an analytics event record.",
    response_model=AnalyticsEventOut,
)
# PUBLIC_INTERFACE
def post_analytics_event(payload: AnalyticsEventIn, db: Session = Depends(get_db)):
    """Insert an analytics event."""
    event = repo.insert_analytics_event(db, payload.user_id, payload.event_name, payload.properties)
    return AnalyticsEventOut(**event)


@app.get(
    "/analytics/summary",
    tags=["Analytics"],
    summary="Analytics summary",
    description="Returns counts of analytics events by name for a date range.",
    response_model=AnalyticsSummaryOut,
)
# PUBLIC_INTERFACE
def get_analytics_summary(
    from_day: Optional[date] = Query(None, description="Start day (YYYY-MM-DD)"),
    to_day: Optional[date] = Query(None, description="End day (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Get analytics summary."""
    data = repo.analytics_summary(db, from_day, to_day)
    return AnalyticsSummaryOut(**data)


@app.get(
    "/admin/users",
    tags=["Admin"],
    summary="List users (admin)",
    description="Lists users for admin dashboards (MVP: no auth enforced).",
    response_model=PagedResponse,
)
# PUBLIC_INTERFACE
def admin_list_users(
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset"),
    db: Session = Depends(get_db),
):
    """Admin list users."""
    data = repo.list_users(db, limit, offset)
    return {
        "items": [UserOut(**x).model_dump() for x in data["items"]],
        "total": data["total"],
        "limit": limit,
        "offset": offset,
    }


@app.get(
    "/docs/ws",
    tags=["Health"],
    summary="WebSocket usage (not implemented)",
    description="Placeholder documentation for future real-time speech feedback WebSocket endpoint.",
)
# PUBLIC_INTERFACE
def websocket_docs():
    """WebSocket usage placeholder.

    Note:
      This project plans a WebSocket endpoint for real-time practice feedback,
      but it is not implemented in this step.
    """
    raise HTTPException(status_code=501, detail="WebSocket endpoints not implemented yet")
