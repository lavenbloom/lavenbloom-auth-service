from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app import models, schemas, auth, database
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    models.Base.metadata.create_all(bind=database.engine)
    yield

app = FastAPI(title="Auth Service", lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Username or email already registered",
            "content": {
                "application/json": {
                    "examples": {
                        "username_taken": {
                            "summary": "Username already registered",
                            "value": {"detail": "Username already registered"}
                        },
                        "email_taken": {
                            "summary": "Email already registered",
                            "value": {"detail": "Email already registered"}
                        }
                    }
                }
            }
        }
    }
)
def register_user(user: schemas.UserCreate, db: Annotated[Session, Depends(database.get_db)]):
    db_user = db.scalar(select(models.User).where(models.User.username == user.username))
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_email = db.scalar(select(models.User).where(models.User.email == user.email))
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(database.get_db)]):
    user = db.scalar(select(models.User).where(models.User.username == form_data.username))
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username, "id": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
