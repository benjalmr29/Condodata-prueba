from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from api.config import settings


bearer_scheme = HTTPBearer(auto_error=True)


class TokenPayload(BaseModel):
    sub: str
    condominio_id: int
    exp: datetime


class TokenData(BaseModel):
    user_id: str
    condominio_id: int


def create_access_token(user_id: str, condominio_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "condominio_id": condominio_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return TokenPayload(**raw)
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),  # noqa: B008
) -> TokenData:
    payload = _decode_token(credentials.credentials)
    if datetime.now(timezone.utc) > payload.exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenData(user_id=payload.sub, condominio_id=payload.condominio_id)
