from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from .user import UserSummary

class ServiceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=2000)
    is_offering: bool

class ServiceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    is_offering: Optional[bool] = None
    is_active: Optional[bool] = None

class ServiceSummary(BaseModel):
    id: int
    title: str
    is_offering: bool
    user: UserSummary
    created_at: datetime

    model_config = ConfigDict(from_attributes = True)

class ServiceRead(BaseModel):
    id: int
    title: str
    description: str
    is_offering: bool
    is_active: bool
    created_at: datetime
    user: UserSummary

    model_config = ConfigDict(from_attributes = True)
