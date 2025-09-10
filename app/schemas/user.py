from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime
import re

class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=20)
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=200)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=20)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    location: Optional[str] = Field(None, max_length=200)

    email_private: Optional[bool] = None
    first_name_private: Optional[bool] = None
    last_name_private: Optional[bool] = None
    bio_private: Optional[bool] = None
    location_private: Optional[bool] = None
    created_at_private: Optional[bool] = None
    is_active_private: Optional[bool] = None

    email_notifications_events: Optional[bool] = None
    email_notifications_messages: Optional[bool] = None
    email_notifications_newsletter: Optional[bool] = None

class UserSummary(BaseModel):
    id: int
    display_name: str
    profile_image_url: Optional[str] = None

class UserPublic(BaseModel):
    id: int
    display_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    profile_image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes = True)

class UserAdmin(BaseModel):
    id: int
    display_name: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    profile_image_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class UserPrivate(BaseModel):
    id: int
    display_name: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    profile_image_url: Optional[str] = None

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

    model_config = ConfigDict(from_attributes = True)
