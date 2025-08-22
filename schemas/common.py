from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime

class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    invalid_value: Optional[Any] = None

class ValidationErrorResponse(BaseModel):
    error: str = "Validation Error"
    details: List[ValidationErrorDetail]
    timestamp: datetime
