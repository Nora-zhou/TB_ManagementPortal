# Feature Specification: Lightweight Task Manager

**Feature Branch**: `001-initial-app`

**Created**: 2026-05-25

**Status**: Draft

## Overview

Build a lightweight task manager web application. Users can create, view, update, and delete tasks. Each task has a title, optional description, status, and priority. The application uses a Python FastAPI backend and a Vue 3 frontend.

## User Scenarios & Testing

### User Story 1 - View & Create Tasks (Priority: P1)

As a user, I can see all my tasks on a dashboard and quickly add new ones.

**Why this priority**: Core functionality — without viewing and creating tasks, the app has no value.

**Independent Test**: Open the app, view the task list, create a new task, and confirm it appears in the list.

**Acceptance Scenarios**:

1. **Given** the app is open, **When** I load the page, **Then** I see a list of all existing tasks.
2. **Given** I am on the dashboard, **When** I fill in the new task form and click "Add", **Then** the task appears at the top of the list without a page reload.
3. **Given** no tasks exist, **When** I load the page, **Then** I see an empty-state message.

---

### User Story 2 - Update Task Status (Priority: P2)

As a user, I can mark a task as in-progress or done directly from the list.

**Why this priority**: Status management is the primary way users track progress.

**Independent Test**: Click the status badge on any task to cycle through statuses; confirm the change persists after page refresh.

**Acceptance Scenarios**:

1. **Given** a task with status "todo", **When** I click "Mark In Progress", **Then** the task status updates to "in_progress".
2. **Given** a task with status "in_progress", **When** I click "Mark Done", **Then** the task status updates to "done" and is visually distinguished.

---

### User Story 3 - Delete Tasks (Priority: P3)

As a user, I can delete tasks I no longer need.

**Why this priority**: Housekeeping — important but not blocking for MVP.

**Independent Test**: Click the delete button on a task, confirm a prompt, and verify the task is removed from the list.

**Acceptance Scenarios**:

1. **Given** a task exists, **When** I click "Delete" and confirm, **Then** the task is removed from the list.
2. **Given** I click "Delete", **When** I cancel the confirmation, **Then** the task remains unchanged.

---

### Edge Cases

- What happens when the API is unreachable? Show a user-friendly error banner.
- What happens if a task title is empty? Prevent submission and show validation message.
- What happens with very long task titles? Truncate with ellipsis in the list view.
