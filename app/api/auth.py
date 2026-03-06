from typing import Optional
from fastapi import Header, HTTPException

from app.config import get_settings


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    required = get_settings().kernel_api_key
    if not required:
        return
    if not x_api_key or x_api_key != required:
        raise HTTPException(status_code=401, detail="Unauthorized")
