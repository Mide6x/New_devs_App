import base64
import io
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import text

from ...core.auth import authenticate_request
from ...core.database_pool import db_pool
from ...models.auth import AuthenticatedUser
from ...models.profile import (
    AvatarUploadResponse,
    NotificationPreference,
    NotificationPreferenceUpdate,
    ProfileResponse,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfile,
    UserProfileUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024
AVATAR_SIZE = (300, 300)

PROFILE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        bio TEXT,
        phone TEXT,
        department TEXT,
        job_title TEXT,
        location TEXT,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        language TEXT NOT NULL DEFAULT 'en',
        theme TEXT NOT NULL DEFAULT 'light',
        avatar_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id TEXT PRIMARY KEY,
        notification_email BOOLEAN NOT NULL DEFAULT TRUE,
        notification_push BOOLEAN NOT NULL DEFAULT TRUE,
        notification_desktop BOOLEAN NOT NULL DEFAULT TRUE,
        notification_sound BOOLEAN NOT NULL DEFAULT TRUE,
        auto_refresh BOOLEAN NOT NULL DEFAULT TRUE,
        compact_view BOOLEAN NOT NULL DEFAULT FALSE,
        sidebar_collapsed BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_preferences (
        user_id TEXT NOT NULL,
        category TEXT NOT NULL,
        email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        push_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        desktop_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        sound_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, category)
    )
    """,
)


async def get_local_session():
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise HTTPException(status_code=503, detail="Local database is unavailable")
    return db_pool.get_session()


async def ensure_profile_records(session, user: AuthenticatedUser) -> None:
    for statement in PROFILE_TABLES:
        await session.execute(text(statement))

    await session.execute(text("""
        INSERT INTO user_profiles (user_id, display_name)
        VALUES (:user_id, :display_name)
        ON CONFLICT (user_id) DO NOTHING
    """), {"user_id": user.id, "display_name": user.email.split("@")[0]})
    await session.execute(text("""
        INSERT INTO user_preferences (user_id)
        VALUES (:user_id)
        ON CONFLICT (user_id) DO NOTHING
    """), {"user_id": user.id})
    await session.execute(text("""
        INSERT INTO notification_preferences (user_id, category)
        VALUES
            (:user_id, 'general'),
            (:user_id, 'reservations'),
            (:user_id, 'payments')
        ON CONFLICT (user_id, category) DO NOTHING
    """), {"user_id": user.id})
    await session.commit()


def row_data(row) -> dict:
    return dict(row._mapping)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image(image_data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(image_data))
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()
    except Exception as error:
        logger.error("Could not process avatar: %s", error)
        raise HTTPException(status_code=400, detail="Invalid image file") from error


@router.get("", response_model=ProfileResponse)
async def get_profile(user: AuthenticatedUser = Depends(authenticate_request)):
    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        profile = (await session.execute(text("SELECT * FROM user_profiles WHERE user_id = :user_id"), {"user_id": user.id})).one()
        preferences = (await session.execute(text("SELECT * FROM user_preferences WHERE user_id = :user_id"), {"user_id": user.id})).one()
        notifications = (await session.execute(text("""
            SELECT * FROM notification_preferences WHERE user_id = :user_id ORDER BY category
        """), {"user_id": user.id})).fetchall()
        return ProfileResponse(
            profile=UserProfile(id=f"profile-{user.id}", **row_data(profile)),
            preferences=UserPreferences(id=f"preferences-{user.id}", **row_data(preferences)),
            notification_preferences=[NotificationPreference(id=f"notification-{user.id}-{row.category}", **row_data(row)) for row in notifications],
            unread_count=0,
        )


@router.put("", response_model=UserProfile)
async def update_profile(profile_update: UserProfileUpdate, user: AuthenticatedUser = Depends(authenticate_request)):
    changes = profile_update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        setters = ", ".join(f"{field} = :{field}" for field in changes)
        result = await session.execute(text(f"""
            UPDATE user_profiles SET {setters}, updated_at = NOW()
            WHERE user_id = :user_id RETURNING *
        """), {**changes, "user_id": user.id})
        await session.commit()
        row = result.one()
        return UserProfile(id=f"profile-{user.id}", **row_data(row))


@router.put("/preferences", response_model=UserPreferences)
async def update_preferences(preferences_update: UserPreferencesUpdate, user: AuthenticatedUser = Depends(authenticate_request)):
    changes = preferences_update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        setters = ", ".join(f"{field} = :{field}" for field in changes)
        result = await session.execute(text(f"""
            UPDATE user_preferences SET {setters}, updated_at = NOW()
            WHERE user_id = :user_id RETURNING *
        """), {**changes, "user_id": user.id})
        await session.commit()
        row = result.one()
        return UserPreferences(id=f"preferences-{user.id}", **row_data(row))


@router.put("/notification-preferences/{category}", response_model=NotificationPreference)
async def update_notification_preference(category: str, preference_update: NotificationPreferenceUpdate, user: AuthenticatedUser = Depends(authenticate_request)):
    changes = {key: value for key, value in preference_update.model_dump(exclude_unset=True).items() if value is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        setters = ", ".join(f"{field} = EXCLUDED.{field}" for field in changes)
        columns = ", ".join(["user_id", "category", *changes])
        values = ", ".join([":user_id", ":category", *[f":{field}" for field in changes]])
        result = await session.execute(text(f"""
            INSERT INTO notification_preferences ({columns}) VALUES ({values})
            ON CONFLICT (user_id, category) DO UPDATE SET {setters}, updated_at = NOW()
            RETURNING *
        """), {**changes, "user_id": user.id, "category": category})
        await session.commit()
        row = result.one()
        return NotificationPreference(id=f"notification-{user.id}-{category}", **row_data(row))


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(file: UploadFile = File(...), user: AuthenticatedUser = Depends(authenticate_request)):
    if not file.filename or not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Please choose a PNG, JPG, JPEG, WEBP, or GIF image")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB")

    avatar_url = "data:image/jpeg;base64," + base64.b64encode(resize_image(content)).decode("ascii")
    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        await session.execute(text("""
            UPDATE user_profiles SET avatar_url = :avatar_url, updated_at = NOW() WHERE user_id = :user_id
        """), {"avatar_url": avatar_url, "user_id": user.id})
        await session.commit()
    return AvatarUploadResponse(avatar_url=avatar_url, message="Avatar uploaded successfully")


@router.delete("/avatar")
async def delete_avatar(user: AuthenticatedUser = Depends(authenticate_request)):
    async with await get_local_session() as session:
        await ensure_profile_records(session, user)
        await session.execute(text("""
            UPDATE user_profiles SET avatar_url = NULL, updated_at = NOW() WHERE user_id = :user_id
        """), {"user_id": user.id})
        await session.commit()
    return {"message": "Avatar deleted successfully"}
