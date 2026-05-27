import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool

from main import app
from database import get_session

TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_list_tasks_empty(client: TestClient):
    response = client.get("/api/tasks/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_task(client: TestClient):
    response = client.post("/api/tasks/", json={"title": "Test task", "priority": "high"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test task"
    assert data["status"] == "todo"
    assert data["priority"] == "high"
    assert "id" in data


def test_create_task_empty_title(client: TestClient):
    response = client.post("/api/tasks/", json={"title": ""})
    assert response.status_code == 422


def test_update_task_status(client: TestClient):
    create_resp = client.post("/api/tasks/", json={"title": "Update me"})
    task_id = create_resp.json()["id"]

    update_resp = client.put(f"/api/tasks/{task_id}", json={"status": "in_progress"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "in_progress"


def test_delete_task(client: TestClient):
    create_resp = client.post("/api/tasks/", json={"title": "Delete me"})
    task_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/tasks/{task_id}")
    assert del_resp.status_code == 204

    list_resp = client.get("/api/tasks/")
    assert all(t["id"] != task_id for t in list_resp.json())


def test_delete_nonexistent_task(client: TestClient):
    response = client.delete("/api/tasks/99999")
    assert response.status_code == 404
