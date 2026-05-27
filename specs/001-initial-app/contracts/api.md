# API Contracts: Task Manager

**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)

## Base URL
`/api` (proxied by Vite to `http://localhost:8000`)

---

## GET /api/tasks

Returns all tasks ordered by creation date descending.

**Response 200**
```json
[
  {
    "id": 1,
    "title": "Set up spec-kit project",
    "description": "Initialize project with FastAPI + Vue 3",
    "status": "done",
    "priority": "high",
    "created_at": "2026-05-25T10:00:00Z"
  }
]
```

---

## POST /api/tasks

Create a new task.

**Request Body**
```json
{
  "title": "string (required, 1-200 chars)",
  "description": "string (optional)",
  "priority": "low | medium | high (default: medium)"
}
```

**Response 201**
```json
{ "id": 2, "title": "...", "status": "todo", "priority": "medium", "created_at": "..." }
```

**Response 422** — Validation error (empty title, invalid priority)

---

## PUT /api/tasks/{id}

Update an existing task's title, description, status, or priority.

**Request Body** (all fields optional)
```json
{
  "title": "string",
  "description": "string",
  "status": "todo | in_progress | done",
  "priority": "low | medium | high"
}
```

**Response 200** — Updated task object

**Response 404** — Task not found

---

## DELETE /api/tasks/{id}

Delete a task by ID.

**Response 204** — No content

**Response 404** — Task not found
