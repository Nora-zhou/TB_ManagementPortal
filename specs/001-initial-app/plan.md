# Implementation Plan: Lightweight Task Manager

**Branch**: `001-initial-app` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

## Summary

Lightweight task manager with a Python FastAPI REST backend and Vue 3 (Vite) frontend. Tasks are persisted in SQLite via SQLModel. Frontend communicates with the backend through a Vite proxy.

## Technical Context

**Language/Version**: Python 3.11+, Node.js 18+

**Primary Dependencies**:
- Backend: `fastapi`, `uvicorn[standard]`, `sqlmodel`, `pydantic`
- Frontend: `vue@3`, `vite`, `@vitejs/plugin-vue`

**Storage**: SQLite (via SQLModel, zero-config, file-based)

**Testing**: `pytest`, `httpx` (backend); Vitest (frontend, optional)

**Target Platform**: Local development / Linux/Windows server

**Project Type**: Full-stack web application

**Performance Goals**: < 100ms API response for typical CRUD operations

**Constraints**: No external services, no Docker required for local dev, minimal npm packages

**Scale/Scope**: Single-user local app, ~5 API endpoints

## Constitution Check

- [x] Simplicity First — SQLite + minimal deps, no auth complexity
- [x] Type Safety — Pydantic models for all API schemas, Vue props typed
- [x] API Contract Clarity — FastAPI auto-generates `/docs` (Swagger UI)
- [x] Separation of Concerns — backend in `backend/`, frontend in `frontend/`

## Project Structure

### Documentation

```text
specs/001-initial-app/
├── spec.md          # Feature specification
├── plan.md          # This file
├── contracts/
│   └── api.md       # API endpoint contracts
└── tasks.md         # Implementation tasks
```

### Source Code

```text
backend/
├── main.py          # FastAPI app, CORS, router registration
├── database.py      # SQLModel engine + session dependency
├── models.py        # SQLModel table definitions (Task)
├── schemas.py       # Pydantic request/response schemas
├── routes/
│   └── tasks.py     # CRUD endpoints for /tasks
└── requirements.txt

frontend/
├── index.html
├── vite.config.js   # Proxy /api → http://localhost:8000
├── package.json
└── src/
    ├── main.js
    ├── App.vue
    ├── api/
    │   └── tasks.js     # Fetch wrapper for task endpoints
    └── components/
        ├── TaskList.vue
        ├── TaskItem.vue
        └── TaskForm.vue
```

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/tasks | List all tasks |
| POST | /api/tasks | Create a task |
| PUT | /api/tasks/{id} | Update a task |
| DELETE | /api/tasks/{id} | Delete a task |

## Data Model

```python
class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = Field(default="todo")   # todo | in_progress | done
    priority: str = Field(default="medium")  # low | medium | high
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173 | Backend API at http://localhost:8000 | Swagger UI at http://localhost:8000/docs
