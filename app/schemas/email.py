from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional

class SubmitEmailDto(BaseModel):
    phoneNumber: Optional[str] = None
    email: Optional[EmailStr] = None
    message: Optional[str] = None