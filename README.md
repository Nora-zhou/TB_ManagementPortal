# ?? Spec Kit App

A lightweight task manager built with **Spec-Driven Development** using [GitHub Spec Kit](https://github.com/github/spec-kit).

**Stack**: Python FastAPI ¡¤ SQLite ¡¤ Vue 3 ¡¤ Vite

---

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API at http://localhost:8000 | Swagger UI at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at http://localhost:5173

---

## Project Structure

```
spec-kit-app/
©À©¤©¤ .specify/                # Spec Kit config & templates
©À©¤©¤ .github/prompts/         # Copilot slash commands (speckit.*)
©À©¤©¤ specs/001-initial-app/   # Spec artifacts for this feature
©¦   ©À©¤©¤ spec.md              # Feature spec (user stories)
©¦   ©À©¤©¤ plan.md              # Technical implementation plan
©¦   ©À©¤©¤ tasks.md             # Actionable task checklist
©¦   ©¸©¤©¤ contracts/api.md     # API endpoint contracts
©À©¤©¤ backend/
©¦   ©À©¤©¤ main.py              # FastAPI app entry point
©¦   ©À©¤©¤ database.py          # SQLModel engine + session
©¦   ©À©¤©¤ models.py            # SQLModel table: Task
©¦   ©À©¤©¤ schemas.py           # Pydantic request/response schemas
©¦   ©À©¤©¤ routes/tasks.py      # CRUD endpoints: /api/tasks
©¦   ©¸©¤©¤ tests/test_tasks.py  # pytest test suite (6 tests)
©¸©¤©¤ frontend/src/
    ©À©¤©¤ App.vue              # Root component
    ©À©¤©¤ api/tasks.js         # Fetch wrapper
    ©¸©¤©¤ components/          # TaskForm, TaskItem, TaskList
```

---

## Spec-Driven Workflow (for future features)

| Command | Purpose |
|---------|---------|
| `/speckit.specify` | Define a new feature (user stories) |
| `/speckit.clarify` | De-risk ambiguities before planning |
| `/speckit.plan` | Create a technical plan |
| `/speckit.tasks` | Generate actionable tasks |
| `/speckit.implement` | Execute tasks to build the feature |

Run `python -m pytest tests/ -v` in `backend/` to verify the API.
