from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from datetime import datetime
import re

class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=20)
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=1000)
    location: str | None = Field(None, max_length=200)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class UserUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=2, max_length=20)
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=1000)
    location: str | None = Field(None, max_length=200)

    email_private: bool | None = None
    first_name_private: bool | None = None
    last_name_private: bool | None = None
    bio_private: bool | None = None
    location_private: bool | None = None
    created_at_private: bool | None = None
    is_active_private: bool | None = None

    email_notifications_events: bool | None = None
    email_notifications_messages: bool | None = None
    email_notifications_newsletter: bool | None = None

class UserSummary(BaseModel):
    id: int
    display_name: str
    profile_image_url: str | None = None
    created_at: datetime

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    location: str | None = None
    created_at: datetime | None = None
    profile_image_url: str | None = None

class UserAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    location: str | None = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    email_verified: bool
    email_verified_at: datetime | None = None
    profile_image_url: str | None = None

class UserPrivate(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    display_name: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    location: str | None = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    email_verified: bool
    email_verified_at: datetime | None = None
    profile_image_url: str | None = None

    email_private: bool
    first_name_private: bool
    last_name_private: bool
    bio_private: bool
    location_private: bool
    created_at_private: bool
    is_active_private: bool

    email_notifications_events: bool
    email_notifications_messages: bool
    email_notifications_newsletter: bool
