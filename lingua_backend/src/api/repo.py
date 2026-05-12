from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session


def _row_to_dict(row: Any) -> Dict[str, Any]:
    # SQLAlchemy Row supports _mapping for dict-like access.
    return dict(row._mapping)  # type: ignore[attr-defined]


def _http_404(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


def list_lessons(
    db: Session,
    language: Optional[str],
    level: Optional[str],
    published_only: bool,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    where = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if language:
        where.append("language = :language")
        params["language"] = language
    if level:
        where.append("level = :level")
        params["level"] = level
    if published_only:
        where.append("is_published = true")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(text(f"SELECT count(*) AS c FROM lesson {where_sql}"), params).scalar_one()

    rows: Result = db.execute(
        text(
            f"""
            SELECT id, slug, title, description, level, language, order_index, is_published
            FROM lesson
            {where_sql}
            ORDER BY order_index ASC, created_at ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    return {"items": [_row_to_dict(r) for r in rows], "total": int(total)}


def get_lesson(db: Session, lesson_id: UUID) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, slug, title, description, level, language, order_index, is_published
            FROM lesson
            WHERE id = :lesson_id
            """
        ),
        {"lesson_id": lesson_id},
    ).mappings().first()
    if not row:
        raise _http_404("Lesson")
    return dict(row)


def list_exercises_for_lesson(db: Session, lesson_id: UUID) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id, lesson_id, slug, title, prompt, exercise_type::text AS exercise_type, content, order_index
            FROM exercise
            WHERE lesson_id = :lesson_id
            ORDER BY order_index ASC, created_at ASC
            """
        ),
        {"lesson_id": lesson_id},
    ).mappings().all()
    # If lesson doesn't exist, return 404 (helps frontend distinguish empty vs bad id)
    lesson_exists = db.execute(
        text("SELECT 1 FROM lesson WHERE id = :lesson_id"),
        {"lesson_id": lesson_id},
    ).first()
    if not lesson_exists:
        raise _http_404("Lesson")
    return [dict(r) for r in rows]


def create_attempt(
    db: Session,
    user_id: UUID,
    exercise_id: UUID,
    answer: Dict[str, Any],
) -> Dict[str, Any]:
    # Validate foreign keys exist
    user_exists = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :user_id"), {"user_id": user_id}
    ).first()
    if not user_exists:
        raise _http_404("User")
    exercise_exists = db.execute(
        text("SELECT 1 FROM exercise WHERE id = :exercise_id"),
        {"exercise_id": exercise_id},
    ).first()
    if not exercise_exists:
        raise _http_404("Exercise")

    row = db.execute(
        text(
            """
            INSERT INTO exercise_attempt (user_id, exercise_id, status, answer, feedback)
            VALUES (:user_id, :exercise_id, 'submitted', :answer::jsonb, '')
            RETURNING
              id, user_id, exercise_id, status::text AS status, answer, score, feedback,
              created_at, submitted_at, graded_at
            """
        ),
        {"user_id": user_id, "exercise_id": exercise_id, "answer": answer},
    ).mappings().first()
    assert row is not None

    # Simple MVP grading:
    # - If exercise content includes correctIndex or correctText, compare and score.
    # - Else keep score NULL and feedback generic.
    ex = db.execute(
        text("SELECT content FROM exercise WHERE id = :exercise_id"),
        {"exercise_id": exercise_id},
    ).mappings().first()
    content = dict(ex)["content"] if ex else {}
    score: Optional[float] = None
    feedback = ""

    try:
        if isinstance(content, dict):
            if "correctIndex" in content and "selectedIndex" in answer:
                score = 100.0 if answer.get("selectedIndex") == content.get("correctIndex") else 0.0
                feedback = "Correct!" if score == 100.0 else "Not quite — try again."
            elif "correctText" in content and "text" in answer:
                score = 100.0 if str(answer.get("text")).strip().lower() == str(content.get("correctText")).strip().lower() else 0.0
                feedback = "Nice work." if score == 100.0 else "Close — check the exact wording."
            elif "targetText" in content and "text" in answer:
                # Speaking stub: fuzzy contains check
                target = str(content.get("targetText", "")).strip().lower()
                said = str(answer.get("text", "")).strip().lower()
                score = 100.0 if target and target in said else 60.0 if said else 0.0
                feedback = "Good pronunciation (stubbed)." if score and score >= 60 else "Try speaking louder/clearer (stubbed)."
    except Exception:
        # Never fail the request due to grading logic; keep attempt saved.
        score = None
        feedback = ""

    if score is not None or feedback:
        updated = db.execute(
            text(
                """
                UPDATE exercise_attempt
                SET status = 'graded', score = :score, feedback = :feedback, graded_at = now(), submitted_at = coalesce(submitted_at, now())
                WHERE id = :attempt_id
                RETURNING
                  id, user_id, exercise_id, status::text AS status, answer, score, feedback,
                  created_at, submitted_at, graded_at
                """
            ),
            {"attempt_id": row["id"], "score": score, "feedback": feedback},
        ).mappings().first()
        if updated:
            return dict(updated)

    return dict(row)


def get_progress(db: Session, user_id: UUID) -> List[Dict[str, Any]]:
    # Validate user exists
    user_exists = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :user_id"), {"user_id": user_id}
    ).first()
    if not user_exists:
        raise _http_404("User")

    rows = db.execute(
        text(
            """
            SELECT user_id, lesson_id, progress_pct, completed_at, last_activity_at
            FROM user_lesson_progress
            WHERE user_id = :user_id
            ORDER BY last_activity_at DESC
            """
        ),
        {"user_id": user_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def upsert_progress(db: Session, user_id: UUID, lesson_id: UUID, progress_pct: float) -> Dict[str, Any]:
    user_exists = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :user_id"), {"user_id": user_id}
    ).first()
    if not user_exists:
        raise _http_404("User")
    lesson_exists = db.execute(
        text("SELECT 1 FROM lesson WHERE id = :lesson_id"), {"lesson_id": lesson_id}
    ).first()
    if not lesson_exists:
        raise _http_404("Lesson")

    completed_at_sql = "now()" if progress_pct >= 100 else "NULL"

    row = db.execute(
        text(
            f"""
            INSERT INTO user_lesson_progress (user_id, lesson_id, progress_pct, completed_at, last_activity_at)
            VALUES (:user_id, :lesson_id, :progress_pct, {completed_at_sql}, now())
            ON CONFLICT (user_id, lesson_id)
            DO UPDATE SET
              progress_pct = EXCLUDED.progress_pct,
              completed_at = CASE WHEN EXCLUDED.progress_pct >= 100 THEN now() ELSE user_lesson_progress.completed_at END,
              last_activity_at = now()
            RETURNING user_id, lesson_id, progress_pct, completed_at, last_activity_at
            """
        ),
        {"user_id": user_id, "lesson_id": lesson_id, "progress_pct": progress_pct},
    ).mappings().first()
    assert row is not None
    return dict(row)


def list_notifications(db: Session, user_id: UUID, limit: int, offset: int) -> Dict[str, Any]:
    user_exists = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :user_id"), {"user_id": user_id}
    ).first()
    if not user_exists:
        raise _http_404("User")

    total = db.execute(
        text("SELECT count(*) AS c FROM notification WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).scalar_one()

    rows = db.execute(
        text(
            """
            SELECT id, user_id, title, body, is_read, created_at
            FROM notification
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"user_id": user_id, "limit": limit, "offset": offset},
    ).mappings().all()

    return {"items": [dict(r) for r in rows], "total": int(total)}


def mark_notification_read(db: Session, user_id: UUID, notification_id: UUID, is_read: bool) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            UPDATE notification
            SET is_read = :is_read
            WHERE id = :notification_id AND user_id = :user_id
            RETURNING id, user_id, title, body, is_read, created_at
            """
        ),
        {"notification_id": notification_id, "user_id": user_id, "is_read": is_read},
    ).mappings().first()
    if not row:
        raise _http_404("Notification")
    return dict(row)


def get_notification_settings(db: Session, user_id: UUID) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT user_id, email_notifications, push_notifications, weekly_digest, updated_at
            FROM notification_settings
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if not row:
        # If missing, create defaults to match DB defaults
        inserted = db.execute(
            text(
                """
                INSERT INTO notification_settings (user_id)
                VALUES (:user_id)
                ON CONFLICT (user_id) DO UPDATE SET updated_at = notification_settings.updated_at
                RETURNING user_id, email_notifications, push_notifications, weekly_digest, updated_at
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        assert inserted is not None
        return dict(inserted)
    return dict(row)


def update_notification_settings(db: Session, user_id: UUID, patch: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure row exists
    get_notification_settings(db, user_id)

    # Build dynamic update
    fields = []
    params: Dict[str, Any] = {"user_id": user_id}
    for key in ("email_notifications", "push_notifications", "weekly_digest"):
        if key in patch and patch[key] is not None:
            fields.append(f"{key} = :{key}")
            params[key] = bool(patch[key])

    if fields:
        set_sql = ", ".join(fields) + ", updated_at = now()"
        row = db.execute(
            text(
                f"""
                UPDATE notification_settings
                SET {set_sql}
                WHERE user_id = :user_id
                RETURNING user_id, email_notifications, push_notifications, weekly_digest, updated_at
                """
            ),
            params,
        ).mappings().first()
        assert row is not None
        return dict(row)

    return get_notification_settings(db, user_id)


def insert_analytics_event(
    db: Session, user_id: Optional[UUID], event_name: str, properties: Dict[str, Any]
) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO analytics_event (user_id, event_name, properties)
            VALUES (:user_id, :event_name, :properties::jsonb)
            RETURNING id, user_id, event_name, properties, created_at
            """
        ),
        {"user_id": user_id, "event_name": event_name, "properties": properties},
    ).mappings().first()
    assert row is not None
    return dict(row)


def analytics_summary(db: Session, from_day: Optional[date], to_day: Optional[date]) -> Dict[str, Any]:
    # Default to last 7 days inclusive
    today = datetime.utcnow().date()
    if to_day is None:
        to_day = today
    if from_day is None:
        from_day = to_day - timedelta(days=6)

    total = db.execute(
        text(
            """
            SELECT count(*) AS c
            FROM analytics_event
            WHERE created_at::date BETWEEN :from_day AND :to_day
            """
        ),
        {"from_day": from_day, "to_day": to_day},
    ).scalar_one()

    rows = db.execute(
        text(
            """
            SELECT event_name, count(*)::int AS c
            FROM analytics_event
            WHERE created_at::date BETWEEN :from_day AND :to_day
            GROUP BY event_name
            ORDER BY c DESC, event_name ASC
            """
        ),
        {"from_day": from_day, "to_day": to_day},
    ).mappings().all()

    return {
        "from_day": from_day,
        "to_day": to_day,
        "total_events": int(total),
        "events_by_name": {r["event_name"]: int(r["c"]) for r in rows},
    }


def list_users(db: Session, limit: int, offset: int) -> Dict[str, Any]:
    total = db.execute(text("SELECT count(*) AS c FROM app_user"), {}).scalar_one()
    rows = db.execute(
        text(
            """
            SELECT id, email, display_name, is_admin, is_premium, created_at
            FROM app_user
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit, "offset": offset},
    ).mappings().all()
    return {"items": [dict(r) for r in rows], "total": int(total)}
