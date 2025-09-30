from pydantic import BaseModel
from datetime import datetime

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    timestamp: datetime

class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    invalid_value: object | None = None

class ValidationErrorResponse(BaseModel):
    error: str = "Validation Error"
    details: list[ValidationErrorDetail]
    timestamp: datetime
