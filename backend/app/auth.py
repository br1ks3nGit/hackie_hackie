from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Driver
from app.services.api_keys import find_active_key, generate_key, hash_key


def hash_api_key(db: Session, api_key: str) -> str:
    """Salted hash of a driver API key; the salt is generated and stored in Postgres."""
    return hash_key(db, api_key)


def generate_api_key() -> str:
    return generate_key()


def get_current_driver(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> Driver:
    driver = db.query(Driver).filter(Driver.api_key_hash == hash_api_key(db, x_api_key)).first()
    if not driver:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return driver


def get_current_insurer(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> None:
    """Insurer endpoints accept any unrevoked key made on the dashboard's API keys screen."""
    if find_active_key(db, x_api_key) is None:
        raise HTTPException(status_code=401, detail="Invalid insurer API key")
