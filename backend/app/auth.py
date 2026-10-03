import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Driver

settings = get_settings()


def hash_api_key(api_key: str) -> str:
    salted = f"{settings.driver_api_key_salt}:{api_key}"
    return hashlib.sha256(salted.encode()).hexdigest()


def verify_api_key(api_key: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_api_key(api_key), hashed)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def get_current_driver(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> Driver:
    driver = db.query(Driver).filter(Driver.api_key_hash == hash_api_key(x_api_key)).first()
    if not driver:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return driver


def get_current_insurer(
    x_api_key: str = Header(...),
) -> None:
    if not hmac.compare_digest(x_api_key, settings.insurer_api_key):
        raise HTTPException(status_code=401, detail="Invalid insurer API key")
