# Tasks: Lightweight Task Manager

**Input**: [plan.md](./plan.md) | [spec.md](./spec.md) | [contracts/api.md](./contracts/api.md)

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel
- **[Story]**: US1/US2/US3

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create `backend/` and `frontend/` directory structure per plan.md
- [ ] T002 Create `backend/requirements.txt` with fastapi, uvicorn[standard], sqlmodel, pydantic, httpx, pytest
- [ ] T003 [P] Initialize Vue 3 + Vite frontend with `npm create vite@latest frontend -- --template vue`
- [ ] T004 [P] Create `backend/database.py` — SQLModel engine (SQLite) + `get_session` dependency
- [ ] T005 [P] Create `backend/models.py` — `Task` SQLModel table with all fields
- [ ] T006 [P] Create `backend/schemas.py` — `TaskCreate`, `TaskUpdate`, `TaskRead` Pydantic schemas
- [ ] T007 Configure `frontend/vite.config.js` with proxy `/api` → `http://localhost:8000`

---

## Phase 2: Backend Implementation

**Purpose**: All REST endpoints required by the API contract

- [ ] T008 [US1] Create `backend/routes/tasks.py` — GET /api/tasks (list all)
- [ ] T009 [US1] Add POST /api/tasks endpoint to routes/tasks.py (create task)
- [ ] T010 [US2] Add PUT /api/tasks/{id} endpoint (update title/description/status/priority)
- [ ] T011 [US3] Add DELETE /api/tasks/{id} endpoint (delete task, return 204)
- [ ] T012 Create `backend/main.py` — FastAPI app, CORS middleware, router mount at `/api`
- [ ] T013 [P] Write `backend/tests/test_tasks.py` — pytest + httpx tests for all 4 endpoints

---

## Phase 3: User Story 1 - View & Create Tasks (Priority: P1) 🎯 MVP

- [ ] T014 Create `frontend/src/api/tasks.js` — fetch wrapper functions (listTasks, createTask, updateTask, deleteTask)
- [ ] T015 Create `frontend/src/components/TaskForm.vue` — form with title (required), description, priority select
- [ ] T016 Create `frontend/src/components/TaskItem.vue` — display single task with status badge and action buttons
- [ ] T017 Create `frontend/src/components/TaskList.vue` — renders list of TaskItem, shows empty state
- [ ] T018 Update `frontend/src/App.vue` — compose TaskForm + TaskList, load tasks on mount, handle create

---

## Phase 4: User Story 2 - Update Task Status (Priority: P2)

- [ ] T019 [US2] Add status-cycle button to TaskItem.vue (todo → in_progress → done → todo)
- [ ] T020 [US2] Wire status update to `updateTask` API call in App.vue

---

## Phase 5: User Story 3 - Delete Tasks (Priority: P3)

- [ ] T021 [US3] Add delete button with `window.confirm` to TaskItem.vue
- [ ] T022 [US3] Wire delete to `deleteTask` API call and remove task from list in App.vue

---

## Phase 6: Polish

- [ ] T023 [P] Add error banner in App.vue for API failures
- [ ] T024 [P] Add basic CSS styling (status badge colors, priority labels, responsive layout)
- [ ] T025 [P] Update `README.md` with setup instructions and spec-kit workflow guide
