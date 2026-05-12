from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApiMessage(BaseModel):
    message: str = Field(..., description="Human-readable message")


class UserOut(BaseModel):
    id: UUID = Field(..., description="User id")
    email: str = Field(..., description="User email")
    display_name: str = Field(..., description="Display name")
    is_admin: bool = Field(..., description="Whether the user is an admin")
    is_premium: bool = Field(..., description="Whether the user has premium access")
    created_at: datetime = Field(..., description="Creation timestamp")


class LessonOut(BaseModel):
    id: UUID = Field(..., description="Lesson id")
    slug: str = Field(..., description="Unique slug")
    title: str = Field(..., description="Title")
    description: str = Field(..., description="Description")
    level: str = Field(..., description="Level (e.g., beginner)")
    language: str = Field(..., description="Language code (e.g., en)")
    order_index: int = Field(..., description="Ordering index")
    is_published: bool = Field(..., description="Whether lesson is published")


ExerciseType = Literal["mcq", "fill_blank", "listening", "speaking"]


class ExerciseOut(BaseModel):
    id: UUID = Field(..., description="Exercise id")
    lesson_id: UUID = Field(..., description="Lesson id")
    slug: str = Field(..., description="Unique slug within the lesson")
    title: str = Field(..., description="Title")
    prompt: str = Field(..., description="Prompt")
    exercise_type: ExerciseType = Field(..., description="Exercise type")
    content: Dict[str, Any] = Field(
        default_factory=dict, description="Flexible exercise payload"
    )
    order_index: int = Field(..., description="Ordering index")


AttemptStatus = Literal["started", "submitted", "graded"]


class AttemptCreateIn(BaseModel):
    user_id: UUID = Field(..., description="User id")
    exercise_id: UUID = Field(..., description="Exercise id")
    answer: Dict[str, Any] = Field(default_factory=dict, description="Attempt answer payload")


class AttemptOut(BaseModel):
    id: UUID = Field(..., description="Attempt id")
    user_id: UUID = Field(..., description="User id")
    exercise_id: UUID = Field(..., description="Exercise id")
    status: AttemptStatus = Field(..., description="Attempt status")
    answer: Dict[str, Any] = Field(default_factory=dict, description="Answer payload")
    score: Optional[float] = Field(None, description="Score 0-100")
    feedback: str = Field(..., description="Feedback text")
    created_at: datetime = Field(..., description="Creation timestamp")
    submitted_at: Optional[datetime] = Field(None, description="Submitted timestamp")
    graded_at: Optional[datetime] = Field(None, description="Graded timestamp")


class ProgressOut(BaseModel):
    user_id: UUID = Field(..., description="User id")
    lesson_id: UUID = Field(..., description="Lesson id")
    progress_pct: float = Field(..., description="Progress percentage 0..100")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    last_activity_at: datetime = Field(..., description="Last activity timestamp")


class ProgressUpsertIn(BaseModel):
    progress_pct: float = Field(..., ge=0, le=100, description="Progress percentage 0..100")


class NotificationSettingsOut(BaseModel):
    user_id: UUID = Field(..., description="User id")
    email_notifications: bool = Field(..., description="Email notifications enabled")
    push_notifications: bool = Field(..., description="Push notifications enabled")
    weekly_digest: bool = Field(..., description="Weekly digest enabled")
    updated_at: datetime = Field(..., description="Updated timestamp")


class NotificationSettingsUpdateIn(BaseModel):
    email_notifications: Optional[bool] = Field(None, description="Email notifications enabled")
    push_notifications: Optional[bool] = Field(None, description="Push notifications enabled")
    weekly_digest: Optional[bool] = Field(None, description="Weekly digest enabled")


class NotificationOut(BaseModel):
    id: UUID = Field(..., description="Notification id")
    user_id: UUID = Field(..., description="User id")
    title: str = Field(..., description="Title")
    body: str = Field(..., description="Body")
    is_read: bool = Field(..., description="Whether read")
    created_at: datetime = Field(..., description="Created timestamp")


class NotificationMarkReadIn(BaseModel):
    is_read: bool = Field(..., description="Mark as read/unread")


class AnalyticsSummaryOut(BaseModel):
    from_day: date = Field(..., description="Inclusive start date")
    to_day: date = Field(..., description="Inclusive end date")
    total_events: int = Field(..., description="Total analytics events")
    events_by_name: Dict[str, int] = Field(..., description="Counts grouped by event_name")


class AnalyticsEventIn(BaseModel):
    user_id: Optional[UUID] = Field(None, description="User id (optional)")
    event_name: str = Field(..., min_length=1, max_length=200, description="Event name")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Event properties")


class AnalyticsEventOut(BaseModel):
    id: UUID = Field(..., description="Event id")
    user_id: Optional[UUID] = Field(None, description="User id (optional)")
    event_name: str = Field(..., description="Event name")
    properties: Dict[str, Any] = Field(..., description="Event properties")
    created_at: datetime = Field(..., description="Created timestamp")


class PagedResponse(BaseModel):
    items: List[Any] = Field(..., description="Page items")
    total: int = Field(..., description="Total matching records")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Offset")
