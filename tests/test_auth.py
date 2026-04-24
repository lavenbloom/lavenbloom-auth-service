import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup testing environment
os.environ["POSTGRES_URI"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "testsecret"

from app.main import app
from app.database import Base, get_db

engine = create_engine(os.environ["POSTGRES_URI"], connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

def test_register():
    response = client.post("/register", json={"username": "testuser", "email": "test@example.com", "password": "password123"})
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    user_data = response.json()
    assert user_data["username"] == "testuser"
    assert "password" not in user_data
    assert "hashed_password" not in user_data

def test_register_duplicate():
    response = client.post("/register", json={"username": "testuser", "email": "test2@example.com", "password": "password123"})
    assert response.status_code == 400

def test_login_success():
    response = client.post("/login", data={"username": "testuser", "password": "password123"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    assert "access_token" in response.json()

def test_login_failure():
    response = client.post("/login", data={"username": "testuser", "password": "wrongpassword"})
    assert response.status_code == 401
