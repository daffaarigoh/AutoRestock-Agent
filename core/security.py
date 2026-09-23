from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

import logging
from core.config import settings

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_KEY
if SECRET_KEY == "super-secret-enterprise-key-for-autorestock-agent" and settings.APP_ENV != "development":
    logger.warning("SECURITY WARNING: Using default hardcoded SECRET_KEY in non-development environment! Set SECRET_KEY in .env.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

security = HTTPBearer()

class TokenData(BaseModel):
    username: str
    role: str
    tenant_id: str
    token_version: int = 1

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> TokenData:
    return _decode_user(credentials.credentials)


def _decode_user(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        tenant_id: str = payload.get("tenant_id")
        token_version = payload.get("token_version", 1)
        if not all(isinstance(value, str) and value for value in (username, role, tenant_id)):
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        try:
            cols = [desc[0] for desc in conn.execute("DESCRIBE users").fetchall()]
            if "token_version" in cols:
                current = conn.execute("SELECT role, tenant_id, COALESCE(token_version, 1) FROM users WHERE username = ?", [username]).fetchone()
            else:
                current = conn.execute("SELECT role, tenant_id, 1 FROM users WHERE username = ?", [username]).fetchone()
        finally:
            conn.close()
        if not current:
            raise HTTPException(status_code=401, detail="User session is no longer valid")
        db_role, db_tenant, db_version = current
        if db_role != role or db_tenant != tenant_id or int(db_version) != int(token_version):
            raise HTTPException(status_code=401, detail="Token revoked or session expired")
        token_data = TokenData(username=username, role=role, tenant_id=tenant_id, token_version=int(db_version))
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_document_user(request: Request) -> TokenData:
    """Allow bearer auth or the HTTP-only cookie for browser PDF navigation only."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.cookies.get("document_session")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _decode_user(token)

def get_current_admin(current_user: TokenData = Security(get_current_user)) -> TokenData:
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Not enough permissions. Admin required.")
    return current_user
