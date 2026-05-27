# Spec Kit App Constitution

## Core Principles

### I. Simplicity First
Keep the codebase lean and readable. Avoid over-engineering. Follow YAGNI - only build what the current spec requires. Every dependency must be justified.

### II. Type Safety (NON-NEGOTIABLE)
All Python code uses type hints (Pydantic models, FastAPI schemas). Vue 3 uses Composition API with proper prop/emit definitions. No untyped values.

### III. API Contract Clarity
All backend endpoints are documented via FastAPI's auto-generated OpenAPI schema. Frontend communicates exclusively through typed API calls.

### IV. Test-First Where Practical
Unit tests accompany all business logic in the backend. Frontend component tests cover critical user flows.

### V. Separation of Concerns
Backend owns all data persistence and business rules. Frontend owns all presentation logic. Never mix concerns across the stack.

## Security Requirements
- Input validation via Pydantic at all API boundaries
- CORS restricted to known origins in production
- No secrets or credentials in source code - use environment variables

## Development Workflow
- Backend runs on port 8000, frontend on port 5173 (Vite default)
- Frontend proxies API calls to backend via Vite server.proxy
- Changes to API contracts require updating both backend schema and frontend types

## Governance
This constitution supersedes all other practices. All implementation decisions must be consistent with these principles.

**Version**: 1.0.0 | **Ratified**: 2026-05-25 | **Last Amended**: 2026-05-25
