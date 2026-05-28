# Spec Kit App

A Taobao store management portal built with **Spec-Driven Development** using [GitHub Spec Kit](https://github.com/github/spec-kit).

**Stack**: Python FastAPI + SQLite + Vue 3 + Vite

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
+-- .specify/                # Spec Kit config & templates
+-- .github/prompts/         # Copilot slash commands (speckit.*)
+-- specs/001-initial-app/   # Spec artifacts for this feature
|   +-- spec.md              # Feature spec (user stories)
|   +-- plan.md              # Technical implementation plan
|   +-- tasks.md             # Actionable task checklist
|   \-- contracts/api.md     # API endpoint contracts
+-- backend/
|   +-- main.py              # FastAPI app entry point
|   +-- database.py          # SQLModel engine + session
|   +-- models.py            # SQLModel table definitions
|   +-- schemas.py           # Pydantic request/response schemas
|   +-- routes/              # CRUD endpoints
|   \-- tests/               # pytest test suite
\-- frontend/src/
    +-- App.vue              # Root component
    +-- api/                 # Fetch wrappers
    \-- components/          # Vue components
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