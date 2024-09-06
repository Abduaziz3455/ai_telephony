from datetime import datetime, timezone, timedelta
from typing import Annotated

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from starlette import status
from starlette.responses import JSONResponse

from db.session import get_db

SECRET_KEY = "6yzVPryC1O3KWMEEUXerlcRzuYDeehWO"
ALGORITHM = "HS256"
EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"}, )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone: str = payload.get("sub")
        if phone is None:
            raise credentials_exception
        token_data = TokenData(phone=phone)
    except InvalidTokenError:
        raise credentials_exception
    user = db.query(Users).filter(Users.phone == token_data.phone).first()
    if user is None:
        raise credentials_exception
    return user


@router.post("/register")
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(Users).filter(Users.phone == user.phone).first()
    if db_user:
        raise HTTPException(status_code=400, detail="User already exists!")

    hashed_password = get_password_hash(user.password)
    db_user = create_user(db, phone=user.phone, password=hashed_password)
    if db_user:
        create_settings(db, user_id=db_user.phone, lang='uz', notification=False, dark_mode=False)
        return JSONResponse(status_code=200, content={"message": "User created successfully!", "phone": db_user.phone})
    else:
        raise HTTPException(status_code=400, detail="Error!")


@router.post("/login", response_model=Token)
async def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(Users).filter(Users.phone == user.phone).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=400, detail="Invalid phone or password")
    access_token_expires = timedelta(days=EXPIRE_DAYS)
    access_token = create_access_token(data={"sub": db_user.phone}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

