# Gurukul Backend Guide

## 1. Purpose and scope

This document is the implementation guide for the separate
`gurukul-backend` repository. It describes how to build, test, operate, and
deploy the Gurukul backend with **FastAPI**.

This document is a guide only. It intentionally does not create backend source
code in the current documentation workspace.

The backend is the authoritative product service. It owns:

- Authentication and authorization
- Users, student profiles, roles, and entitlements
- Subjects, teacher-bot catalog entries, courses, lessons, and content
  metadata
- Conversations and durable message records
- Quiz definitions, attempts, answers, scoring, and feedback records
- Student progress and leaderboard snapshots
- Idempotency, audit events, and integration coordination
- The public API consumed by the separate Next.js frontend

The backend does **not** own:

- OpenRouter credentials or direct model-provider calls
- LangGraph graph definitions
- Prompt implementation
- Embedding generation and vector retrieval internals
- Browser UI state
- The final authority for model-generated educational content

The backend calls the separate `gurukul-ai` service through an authenticated
internal contract. The browser never calls the AI service directly.

---

## 2. Architectural goals

### 2.1 Required qualities

The backend must be:

- **Correct:** scores, ranks, permissions, and durable state must be
  server-authoritative.
- **Reusable:** domain logic should be composed from services and repositories,
  not copied into route handlers.
- **Explicit:** errors, state transitions, permissions, and external failures
  must be visible and diagnosable.
- **Async-friendly:** slow work must move to workers without making requests
  wait unnecessarily.
- **Contract-driven:** frontend and AI integration schemas must be versioned.
- **Observable:** requests, jobs, AI runs, and database operations need
  correlation and timing information.
- **Secure:** secrets, student data, audio, and internal service endpoints
  must be protected.
- **Deployable independently:** frontend, backend, and AI repositories can
  release on different schedules while preserving compatibility.

### 2.2 Recommended initial implementation strategy

Start as a modular monolith:

```text
One FastAPI deployment
One worker deployment
One PostgreSQL database
One Redis instance or managed Redis
One private object-storage bucket
One separately deployed AI service
```

Keep module boundaries strict inside the monolith. This gives the team
transactional consistency and simpler operations without creating premature
microservice overhead. API and worker processes can scale independently. A
module can later be extracted only when measurements justify the cost.

---

## 3. Repository layout

The following is the recommended structure for the separate
`gurukul-backend` repository.

```text
gurukul-backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   ├── router.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── students.py
│   │       ├── subjects.py
│   │       ├── teachers.py
│   │       ├── conversations.py
│   │       ├── messages.py
│   │       ├── voice.py
│   │       ├── quizzes.py
│   │       ├── attempts.py
│   │       ├── progress.py
│   │       ├── leaderboards.py
│   │       ├── notifications.py
│   │       ├── content.py
│   │       └── admin.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── logging.py
│   │   ├── telemetry.py
│   │   ├── security.py
│   │   ├── errors.py
│   │   ├── lifecycle.py
│   │   └── feature_flags.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   ├── transaction.py
│   │   ├── types.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── users.py
│   │   │   ├── students.py
│   │   │   ├── catalog.py
│   │   │   ├── conversations.py
│   │   │   ├── quizzes.py
│   │   │   ├── progress.py
│   │   │   ├── leaderboards.py
│   │   │   ├── audit.py
│   │   │   └── outbox.py
│   │   └── migrations/
│   │       ├── env.py
│   │       ├── script.py.mako
│   │       └── versions/
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── identity.py
│   │   ├── catalog.py
│   │   ├── conversations.py
│   │   ├── assessments.py
│   │   ├── progress.py
│   │   ├── operations.py
│   │   └── content.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── errors.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── students.py
│   │   ├── catalog.py
│   │   ├── conversations.py
│   │   ├── voice.py
│   │   ├── quizzes.py
│   │   ├── progress.py
│   │   ├── leaderboards.py
│   │   ├── content.py
│   │   ├── internal_ai.py
│   │   └── events.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── catalog.py
│   │   ├── conversations.py
│   │   ├── chat.py
│   │   ├── voice.py
│   │   ├── quizzes.py
│   │   ├── scoring.py
│   │   ├── progress.py
│   │   ├── leaderboards.py
│   │   ├── content.py
│   │   ├── notifications.py
│   │   ├── entitlements.py
│   │   ├── audit.py
│   │   └── idempotency.py
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── ai_client.py
│   │   ├── redis.py
│   │   ├── object_storage.py
│   │   ├── email.py
│   │   ├── identity_provider.py
│   │   └── telemetry.py
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── queues.py
│   │   ├── jobs/
│   │   │   ├── __init__.py
│   │   │   ├── leaderboard.py
│   │   │   ├── ai_feedback.py
│   │   │   ├── voice.py
│   │   │   ├── notifications.py
│   │   │   ├── outbox.py
│   │   │   ├── cleanup.py
│   │   │   └── analytics.py
│   │   └── schedules.py
│   │
│   └── templates/
│       └── email/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── api/
│   ├── workers/
│   ├── fixtures/
│   └── conftest.py
│
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── Dockerfile.worker
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── .gitignore
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
└── .github/
    └── workflows/
        ├── ci.yml
        ├── build.yml
        └── deploy.yml
```

The exact names may change, but the dependency direction must remain:

```text
API routes -> application services -> repositories/integrations
schemas    -> API and integration contracts
models     -> database persistence
workers    -> application services
core       -> shared infrastructure only
```

Routes must not contain SQL queries, provider calls, scoring algorithms, or
large business workflows.

---

## 4. File-by-file responsibilities

### 4.1 Application entry points

#### `app/main.py`

This is the FastAPI application factory and process entry point. It should:

- Create the FastAPI application.
- Set title, version, and OpenAPI metadata.
- Register exception handlers.
- Register the versioned API router.
- Register health and readiness endpoints.
- Register startup and shutdown lifecycle handlers.
- Install request ID and tracing middleware.
- Configure CORS from settings.
- Avoid opening database connections at import time.

Prefer an application factory such as `create_app()` so tests can create an
isolated application with overridden dependencies.

#### `app/api/router.py`

This file composes public, internal, health, and metrics routers. It should
not implement business behavior.

#### `app/api/v1/router.py`

This file includes all `/api/v1` public routers and establishes the public
version boundary. A future `/api/v2` should be able to coexist during a
migration period.

### 4.2 API route modules

Each route module should be thin. A route handler should:

1. Parse and validate input through a Pydantic schema.
2. Resolve the authenticated principal.
3. Check route-level permission dependencies.
4. Call one application service method.
5. Translate the result into a response schema.
6. Return an explicit status code.

#### `app/api/v1/auth.py`

Implement registration, login, logout, refresh or session renewal, email
verification, password reset, and current-user lookup. Never return password
hashes, provider tokens, or internal authentication details.

#### `app/api/v1/users.py`

Implement the authenticated user's safe profile view and profile updates.
Sensitive fields require explicit handling and audit logging.

#### `app/api/v1/students.py`

Implement student preferences, grade or level, language, accessibility
settings, consent state, and learning summary. Do not allow a student to
change server-controlled rank or score fields.

#### `app/api/v1/subjects.py`

Return published subjects and their availability. This is mostly cacheable
catalog data.

#### `app/api/v1/teachers.py`

Return enabled teacher-bot catalog entries. Expose display configuration,
supported levels, and capabilities, but never expose hidden system prompts,
provider IDs that should remain internal, or policy secrets.

#### `app/api/v1/conversations.py`

Create and list conversations, fetch conversation metadata, archive or close
conversations, and enforce participant ownership. Message history should be
paginated.

#### `app/api/v1/messages.py`

Submit text messages, retrieve message history, and expose stream negotiation.
The handler should enforce message size, conversation ownership, teacher
availability, and idempotency.

#### `app/api/v1/voice.py`

Create an authorized voice session or upload, report processing status, and
retrieve permitted audio references. Validate size, MIME type, duration, and
retention policy before accepting audio.

#### `app/api/v1/quizzes.py`

List published quizzes, retrieve a quiz version without answer keys, and
expose availability windows. A published quiz version must be immutable.

#### `app/api/v1/attempts.py`

Start an attempt, submit answers, finalize an attempt, retrieve results, and
request permitted feedback. Submission must be idempotent and server-scored.

#### `app/api/v1/progress.py`

Return personal progress, subject summaries, completed lessons, learning
streaks, and improvement metrics. Avoid expensive unbounded queries in a
synchronous request.

#### `app/api/v1/leaderboards.py`

Return the current weekly snapshot, the authenticated student's rank, nearby
students where privacy policy permits, and historical snapshots. Never expose
private profile data merely because two users share a leaderboard.

#### `app/api/v1/notifications.py`

List and mark notifications read. Notification creation belongs to services
and workers, not to this route module.

#### `app/api/v1/content.py`

Provide authorized content-management endpoints for administrators or content
managers. These endpoints create document metadata and queue ingestion; they
do not perform long-running embedding work in the request process.

#### `app/api/v1/admin.py`

Provide carefully scoped operational actions such as publishing a quiz,
enabling a teacher, reviewing a failed job, or viewing aggregate metrics.
Separate admin dependencies and audit every mutation.

### 4.3 Core files

#### `app/core/config.py`

Define typed settings loaded from environment variables. Include:

- Environment name
- API and frontend origins
- Database URL and pool settings
- Redis URL
- Object-storage configuration
- AI service base URL and service-auth settings
- Session and token settings
- CORS and upload limits
- Rate-limit defaults
- Logging and telemetry configuration
- Feature flags

Do not put secret values in source code. Use a secret manager in production.
Fail startup for required missing settings rather than silently selecting an
unsafe default.

#### `app/core/constants.py`

Keep stable enumerations and names here only when they are shared across
modules. Domain-specific constants should live with their domain service.

#### `app/core/logging.py`

Configure structured logs, redaction, log levels, and correlation fields.
Use JSON in deployed environments. Redact authorization headers, cookies,
passwords, audio content, and sensitive student fields.

#### `app/core/telemetry.py`

Configure tracing and metrics. Provide helpers for request spans, AI calls,
database timing, queue jobs, and external errors.

#### `app/core/security.py`

Implement password hashing, session or token validation, service-to-service
request signing, secure token comparison, and security-related helpers.
Keep authorization policy checks in dedicated dependencies or services rather
than scattering them across this file.

#### `app/core/errors.py`

Define typed domain exceptions and public error codes. Each exception should
have a safe client message, an HTTP status, and a log severity. Unexpected
exceptions must be logged with the request ID and returned as a generic 500
response.

#### `app/core/lifecycle.py`

Manage process startup and shutdown. Initialize only process-local resources:
database engine, Redis client, HTTP client, metrics, and queue connections.
Close them reliably during shutdown.

#### `app/core/feature_flags.py`

Expose typed feature flags for controlled rollout. Flags must not bypass
authorization or data validation.

### 4.4 Database files

#### `app/db/base.py`

Import all SQLAlchemy model classes for migration metadata. Do not put
application logic here.

#### `app/db/session.py`

Create the async SQLAlchemy engine, session factory, and request-scoped
session dependency. Configure pool size, overflow, timeout, recycle behavior,
and statement timeout according to deployment settings.

#### `app/db/transaction.py`

Provide explicit transaction helpers. A service should clearly own the
transaction boundary for operations such as registration, attempt submission,
and leaderboard finalization.

#### `app/db/types.py`

Define shared database types such as UTC-aware timestamps, public IDs, JSON
columns, and enumerated states.

#### `app/db/repositories/*.py`

Repositories encapsulate persistence queries. They should:

- Accept a session and typed arguments.
- Return models or typed persistence results.
- Use explicit query projections for list endpoints.
- Apply ownership and visibility filters when that is part of the repository
  contract.
- Avoid calling external services.
- Avoid committing transactions unless explicitly documented.

Application services should combine repositories and external integrations.

#### `app/db/migrations/`

Use Alembic for reviewed, forward migrations. Each migration must:

- Have a descriptive name.
- Be reversible where practical.
- Avoid locking large tables unexpectedly.
- Add indexes concurrently when production size requires it.
- Preserve compatibility with the previous application during rollout.

Never edit an already-applied migration. Create a new migration.

### 4.5 Models

SQLAlchemy models represent persistence, not public API contracts. Keep
response/request schemas separate so database changes do not accidentally
change the frontend API.

#### `app/models/common.py`

Define shared base classes, public ID generation, timestamps, optimistic
version fields where needed, and soft-delete fields only where retention
policy requires them.

#### `app/models/identity.py`

Define `User`, `StudentProfile`, `Role`, `UserRole`, login identities, session
records, verification records, and password-reset records.

#### `app/models/catalog.py`

Define subjects, teacher bots, courses, lessons, teacher capabilities, and
publication state.

#### `app/models/conversations.py`

Define conversations, participants, messages, message attachments, and
assistant response status.

#### `app/models/assessments.py`

Define quizzes, immutable quiz versions, questions, options, attempts,
answers, scoring results, and feedback.

#### `app/models/progress.py`

Define learning events, subject progress, weekly scores, and leaderboard
snapshots.

#### `app/models/operations.py`

Define audit logs, outbox events, idempotency records, notifications, and
job status records.

#### `app/models/content.py`

Define content documents, versions, object-storage references, ingestion
status, approval state, and metadata used to coordinate with the AI service.

### 4.6 Schemas

Pydantic schemas are the public and integration contracts.

Every schema should:

- Reject unexpected or invalid input where appropriate.
- Set maximum lengths and collection sizes.
- Use explicit optionality.
- Use UTC-aware datetimes.
- Avoid exposing persistence-only fields.
- Have stable examples in OpenAPI where useful.

#### `app/schemas/common.py`

Define pagination, sorting, public IDs, timestamps, and request metadata.

#### `app/schemas/errors.py`

Define the common public error envelope:

```json
{
  "error": {
    "code": "MESSAGE_TOO_LARGE",
    "message": "The message exceeds the permitted length.",
    "request_id": "req_01..."
  }
}
```

#### `app/schemas/auth.py`

Define registration, login, refresh, logout, verification, reset, and
authenticated-user response schemas.

#### `app/schemas/catalog.py`

Define public subject, teacher, course, lesson, and capability schemas.
Exclude prompt text and internal provider configuration.

#### `app/schemas/conversations.py` and `messages.py`

Define conversation creation, message submission, message response, stream
events, citations, and terminal stream states.

#### `app/schemas/voice.py`

Define voice-session authorization, upload metadata, processing status, and
audio reference responses.

#### `app/schemas/quizzes.py`

Define quiz list, quiz detail without answer keys, question presentation,
attempt creation, answer submission, and result schemas.

#### `app/schemas/internal_ai.py`

Define the backend-to-AI request and response contract. This contract must
include:

- Request ID and idempotency key
- Opaque user and conversation identifiers
- Teacher and subject identifiers
- Bounded conversation context
- Student level and language preferences
- Requested operation
- Policy and contract versions
- Time and token budgets

Responses should include:

- Run ID
- Status
- Answer or stream data
- Citations when available
- Safety result
- Usage metadata
- Provider-independent failure code

Do not send unnecessary student profile data to the AI service.

#### `app/schemas/events.py`

Define versioned event envelopes and payloads. Treat event schemas as
compatibility contracts for workers and future services.

### 4.7 Services

Services contain business workflows. They should not depend on FastAPI
request objects.

#### `app/services/auth.py`

Coordinate registration, credential verification, session issuance, logout,
verification, reset, and account lockout policy.

#### `app/services/users.py` and `students.py`

Manage profile updates, consent, preferences, and privacy operations.

#### `app/services/catalog.py`

Return published catalog data, manage admin publication state, and invalidate
related caches.

#### `app/services/conversations.py`

Create conversations, enforce participant ownership, paginate messages, and
manage archive state.

#### `app/services/chat.py`

Coordinate message idempotency, entitlement checks, AI calls, streaming,
message persistence, usage records, and failure state. It must not contain
prompt construction or OpenRouter-specific code.

#### `app/services/voice.py`

Coordinate upload authorization, voice status, AI transcription/synthesis
requests, object references, retention, and failure handling.

#### `app/services/quizzes.py`

Manage quiz publication, immutable versions, availability windows, attempts,
and answer submission state transitions.

#### `app/services/scoring.py`

Implement deterministic scoring rules. This module is authoritative for
objective quiz scores and must have extensive tests. AI feedback must not
silently change authoritative points.

#### `app/services/progress.py`

Record learning events and calculate or retrieve student progress. Expensive
aggregations should be materialized asynchronously.

#### `app/services/leaderboards.py`

Calculate weekly scores, apply tie-breaking rules, create immutable snapshots,
and provide privacy-safe reads. Finalization must be idempotent.

#### `app/services/content.py`

Manage document metadata, approval state, signed uploads, and AI ingestion
jobs. The backend owns authorization and publication state; the AI service
owns parsing and embeddings.

#### `app/services/entitlements.py`

Check plan, institution, feature, and usage access. Keep this policy
centralized so chat, voice, and quiz routes do not implement conflicting
rules.

#### `app/services/audit.py`

Create audit records for authentication-sensitive actions, admin mutations,
content publication, score overrides, data export, and deletion.

#### `app/services/idempotency.py`

Reserve and retrieve idempotency keys with request fingerprint, result status,
and expiry. Reusing a key with a different request body must produce a clear
conflict.

### 4.8 Integrations

Integration adapters isolate external systems from domain services.

#### `app/integrations/ai_client.py`

Call the internal AI service over HTTPS. This client must:

- Use a shared async HTTP client.
- Authenticate every request.
- Send a request ID and idempotency key.
- Use connect, read, and total timeouts.
- Validate response schemas.
- Classify retryable versus permanent errors.
- Never log secrets or full sensitive prompts.
- Support streaming with cancellation and terminal-state handling.
- Expose provider-independent errors to application services.

The backend must not call OpenRouter directly. OpenRouter belongs behind the
AI service boundary.

#### `app/integrations/redis.py`

Create a typed Redis adapter for caching, rate limits, idempotency, locks,
queue coordination, and short-lived status. Define key namespaces and TTLs in
one place.

#### `app/integrations/object_storage.py`

Implement private object uploads, signed URLs, metadata checks, deletion, and
lifecycle operations. Validate object ownership before creating a signed URL.

#### `app/integrations/email.py`

Provide email delivery behind an adapter. Queue email delivery instead of
blocking registration or password reset requests.

#### `app/integrations/identity_provider.py`

Keep external identity-provider integration replaceable. Map provider
identities to internal users.

### 4.9 Workers

#### `app/workers/app.py`

Create the worker process and load configuration. Worker startup must not
expose a public HTTP port unless explicitly required.

#### `app/workers/queues.py`

Define queue names, routing, retry policy, visibility timeout, and dead-letter
behavior. Separate interactive follow-up jobs from batch ingestion and
analytics jobs.

#### `app/workers/jobs/leaderboard.py`

Finalize weekly leaderboard snapshots. Acquire a distributed lock, compute
from durable records, write the snapshot transactionally, and mark the job
complete idempotently.

#### `app/workers/jobs/ai_feedback.py`

Request asynchronous AI quiz feedback, validate the response, persist status,
and retry only transient failures.

#### `app/workers/jobs/voice.py`

Coordinate asynchronous transcription or synthesis and update status. Apply
retention cleanup after terminal state.

#### `app/workers/jobs/notifications.py`

Deliver notifications and record attempts. Use bounded retries and a
dead-letter path.

#### `app/workers/jobs/outbox.py`

Publish pending outbox events. Mark events only after successful publication
and ensure duplicate delivery is safe for consumers.

#### `app/workers/jobs/cleanup.py`

Apply retention policies to expired sessions, idempotency keys, temporary
audio, old stream state, and other explicitly approved data.

#### `app/workers/jobs/analytics.py`

Aggregate learning events into reporting tables. Do not run broad analytical
queries on the transactional request path.

---

## 5. Dependency plan

Use `pyproject.toml` as the dependency manifest. Use a lockfile and a single
repository-wide dependency update process. The exact versions should be pinned
after checking compatibility with the selected Python release and deployment
platform.

### 5.1 Runtime dependencies

| Package/category | Purpose | Where used |
|---|---|---|
| `fastapi` | HTTP API framework and OpenAPI generation | API process |
| `uvicorn` | ASGI server | API process |
| `pydantic` | Typed validation and serialization | API, services, integrations |
| `pydantic-settings` | Environment-backed settings | Core configuration |
| `sqlalchemy` | ORM and SQL expression layer | Database |
| `asyncpg` | Async PostgreSQL driver | Database |
| `alembic` | Schema migrations | Release process |
| `redis` | Async Redis client | Cache, limits, jobs |
| Queue library | Redis-backed workers and scheduling | Worker process |
| `httpx` | Async calls to AI and external services | Integrations |
| `PyJWT` or equivalent | Token handling if JWT is selected | Security |
| Password hashing library | Argon2id or another approved adaptive hash | Authentication |
| `python-multipart` | Multipart form and upload parsing | Auth and voice/content upload |
| Object-storage SDK | S3-compatible private storage | Audio and documents |
| `email-validator` | Email validation | Authentication |
| OpenTelemetry packages | Distributed tracing | Observability |
| Prometheus instrumentation | Metrics endpoint/export | Observability |
| Structured logging package | JSON logs and context fields | Operations |

Use only one primary library per responsibility where possible. Do not add a
second ORM, HTTP client, queue system, or settings system without a documented
reason.

### 5.2 Development dependencies

| Package/category | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `httpx` test transport | API client tests |
| Testcontainers or Docker-based fixtures | Real PostgreSQL/Redis integration tests |
| Factory library | Consistent test data |
| Ruff | Formatting and linting |
| Pyright or mypy | Static type checking |
| Coverage tool | Coverage reporting |
| Pre-commit | Local quality hooks |
| Dependency audit tool | Vulnerability checks |
| OpenAPI/code generation tool | Frontend contract generation |

### 5.3 Optional dependencies

Add these only when a requirement is confirmed:

- `pgvector` integration if vector metadata is stored in this repository
- Sentry SDK if the organization selects Sentry
- A managed identity-provider SDK
- A dedicated message broker client
- A billing-provider SDK
- A malware-scanning integration for uploads

The backend should not install LangChain, LangGraph, OpenRouter SDKs, or model
provider SDKs merely because the product has AI features. Those dependencies
belong in `gurukul-ai`.

### 5.4 Dependency policy

- Pin direct dependencies through the lockfile.
- Review transitive changes in pull requests.
- Separate runtime and development dependencies.
- Run vulnerability scanning in CI.
- Do not install packages at runtime.
- Remove unused packages.
- Document any package that handles credentials, cryptography, uploads, or
  code execution.

---

## 6. Configuration and environments

### 6.1 `.env.example`

The example file should document names and safe placeholder values, such as:

```text
APP_ENV=development
APP_NAME=gurukul-backend
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/gurukul
REDIS_URL=redis://localhost:6379/0
FRONTEND_ORIGINS=http://localhost:3000
AI_SERVICE_URL=http://localhost:8001
AI_SERVICE_AUTH_KEY=replace-me
SESSION_SECRET=replace-me
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_SSL=false
SMTP_STARTTLS=true
SMTP_TIMEOUT_SECONDS=10
PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=false
OBJECT_STORAGE_BUCKET=gurukul-local
OBJECT_STORAGE_ENDPOINT=http://localhost:9000
OBJECT_STORAGE_ACCESS_KEY=replace-me
OBJECT_STORAGE_SECRET_KEY=replace-me
OTEL_EXPORTER_OTLP_ENDPOINT=
```

Do not put real credentials in this file or commit local `.env` files.

For local Swagger testing only, set `PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=true`
while `APP_ENV=development`. The password-reset request then returns the OTP
instead of sending an email. This option is ignored outside development; keep it
disabled outside local testing.

### 6.2 Required configuration behavior

- Required production secrets must fail startup when absent.
- Development defaults must be clearly development-only.
- CORS origins must be explicit, not `*` in production.
- Upload limits must be configured centrally.
- Database and Redis TLS settings must be configurable.
- Timeouts must be separate for database, Redis, AI, and object storage.
- Feature flags must have safe production defaults.

---

## 7. Database design

PostgreSQL is the source of truth for all durable product state.

### 7.1 Identity tables

#### `users`

Recommended fields:

```text
id
email
email_normalized
roll_number
password_hash nullable
display_name
status
locale
timezone
created_at
updated_at
last_login_at nullable
deleted_at nullable
```

Rules:

- Unique normalized email.
- Assign a unique, stable roll number at admission. Students may log in with
  their roll number or email; name-based login is allowed only when the name
  identifies exactly one student.
- Never expose `password_hash`.
- Use a status enum for active, pending, suspended, and deleted.
- Soft deletion must comply with the privacy policy and retention rules.

#### `student_profiles`

```text
id
user_id
date_of_birth
grade_level nullable
learning_goals nullable
phone_number
liked_subjects
preferred_language
accessibility_preferences
consent_version
consent_at
created_at
updated_at
```

Keep sensitive or optional profile data separate from `users`.

#### `roles` and `user_roles`

Represent roles such as student, content manager, administrator, and
operations user. Do not use a client-supplied role claim as authorization
authority without server validation.

#### Sessions and identity records

Store refresh/session records only if using server-managed sessions. Store
revocation, expiry, creation source, and a hashed session identifier rather
than reusable raw tokens.

### 7.2 Catalog tables

#### `subjects`

```text
id
slug
name
description
status
display_order
created_at
updated_at
```

#### `teacher_bots`

```text
id
subject_id
slug
display_name
description
grade_range
supported_languages
capabilities
prompt_policy_version
retrieval_policy_version
model_policy_version
status
created_at
updated_at
```

The backend stores versions and public metadata, not hidden prompt bodies.

#### Courses and lessons

Use `courses`, `course_lessons`, and `lessons` for structured learning
content. Track publication state and ordering. If the first release has no
course experience, these tables can be introduced after the subject catalog.

### 7.3 Conversation tables

#### `conversations`

```text
id
student_id
teacher_bot_id
title nullable
status
summary nullable
summary_version nullable
last_message_at
created_at
updated_at
```

#### `messages`

```text
id
conversation_id
role
content
content_format
status
client_message_id nullable
reply_to_message_id nullable
created_at
completed_at nullable
```

Do not store unbounded context in one row. Paginate messages and create
bounded summaries for long conversations.

#### `ai_runs`

```text
id
conversation_id nullable
request_id
message_id nullable
teacher_bot_id nullable
operation
status
contract_version
policy_versions
model_name nullable
provider_name nullable
input_tokens nullable
output_tokens nullable
estimated_cost nullable
latency_ms nullable
safety_status nullable
failure_code nullable
created_at
completed_at nullable
```

Store enough metadata for support and cost analysis. Avoid storing duplicate
raw prompts or sensitive content when references are sufficient.

### 7.4 Assessment tables

#### `quizzes` and `quiz_versions`

Separate the stable quiz identity from immutable versions. A published
version cannot be edited in place.

Recommended fields include:

```text
quizzes: id, subject_id, slug, title, status
quiz_versions: id, quiz_id, version_number, time_limit_seconds,
               available_from, available_until, scoring_policy_version,
               publication_status, created_at, published_at
```

#### Questions and options

Store question type, prompt, explanation, points, ordering, and options.
Answer keys must not be included in the student response schema.

#### Attempts and answers

```text
quiz_attempts:
  id, quiz_version_id, student_id, status, started_at, submitted_at,
  score, max_score, percentage, scoring_version, finalized_at

quiz_answers:
  id, attempt_id, question_id, selected_option_id nullable,
  answer_text nullable, is_correct nullable, points_awarded,
  submitted_at
```

Use constraints to prevent duplicate finalized attempts where policy allows
only one attempt. If multiple attempts are allowed, define exactly how the
best score or latest score contributes to ranking.

### 7.5 Progress and ranking tables

#### `learning_events`

Append-only events such as lesson completion, quiz completion, and learning
milestones. Do not use this table as an unbounded request log.

#### `student_progress`

Store materialized per-student and per-subject summaries for fast reads.
Rebuildable summaries should have a source or calculation version.

#### `weekly_scores`

Store the durable score components that contribute to a week:

```text
id
student_id
week_start
week_end
quiz_points
learning_points
bonus_points
total_points
calculation_version
created_at
updated_at
```

#### `leaderboard_snapshots`

Store immutable published snapshots:

```text
id
week_start
week_end
status
finalized_at
calculation_version
created_at
```

Use a child table for ranked entries with rank, opaque student reference,
score, percentile, and privacy-safe display data. Define deterministic
tie-breaking before implementation.

### 7.6 Content and operations tables

Recommended tables:

- `content_documents`
- `content_versions`
- `content_ingestion_jobs`
- `object_references`
- `notifications`
- `audit_logs`
- `outbox_events`
- `idempotency_records`
- `job_records`

All status fields need documented state transitions and invalid transitions
must produce explicit errors.

---

## 8. API contract for the frontend repository

The frontend repository consumes only the public backend API. Publish the
backend OpenAPI document as a versioned build artifact so the frontend can
generate or validate TypeScript types from the exact contract.

### 8.1 Authentication

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/password-reset/request
POST   /api/v1/auth/password-reset/verify
POST   /api/v1/auth/password-reset/confirm
GET    /api/v1/auth/me
PATCH  /api/v1/auth/me
```

`GET /api/v1/auth/me` returns the authenticated student's profile. `PATCH
/api/v1/auth/me` accepts one or more of `display_name`, `date_of_birth`,
`grade_level` (1–10), `liked_subjects`, and `phone_number`; omitted fields are
unchanged. Roll number is immutable through this endpoint. Email changes require
a separate verification flow, and password changes use a separate endpoint.

Password reset codes are emailed, expire after 10 minutes, are stored only as
keyed hashes, and allow at most five verification attempts. Requests are
throttled per account; reset tokens expire after 15 minutes and are single-use.
Set SMTP configuration before enabling these endpoints.

Registration and login return a 30-minute access token and a 30-day refresh
token. Refresh tokens are opaque, stored only as keyed hashes, and rotated on
every refresh. Reuse of a revoked refresh token revokes all sessions for that
account. Password reset invalidates outstanding access and refresh tokens.
Logout revokes the submitted refresh token; an already-issued access token
may remain valid until its short expiry.

Recommended browser pattern: secure, HTTP-only, same-site cookies for
session/refresh state. If bearer access tokens are used, define storage and
rotation carefully; never place long-lived secrets in local storage by
default.

### 8.2 Profile and catalog

```text
GET    /api/v1/users/me
PATCH  /api/v1/users/me
GET    /api/v1/students/me
PATCH  /api/v1/students/me
GET    /api/v1/subjects
GET    /api/v1/subjects/{subject_id}
GET    /api/v1/teachers
GET    /api/v1/teachers/{teacher_id}
GET    /api/v1/courses
GET    /api/v1/courses/{course_id}
```

Catalog responses should include cache headers or a cache policy where safe.

### 8.3 Conversations and chat

```text
POST   /api/v1/conversations
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversation_id}
PATCH  /api/v1/conversations/{conversation_id}
GET    /api/v1/conversations/{conversation_id}/messages
POST   /api/v1/conversations/{conversation_id}/messages
GET    /api/v1/conversations/{conversation_id}/stream
```

Message creation should accept:

```json
{
  "client_message_id": "client-msg-unique-value",
  "content": "Can you explain fractions?",
  "content_format": "text",
  "stream": true
}
```

The backend owns the server message ID and final status.

### 8.4 Voice

```text
POST   /api/v1/voice/sessions
POST   /api/v1/voice/uploads
GET    /api/v1/voice/jobs/{job_id}
GET    /api/v1/voice/audio/{audio_id}
DELETE /api/v1/voice/audio/{audio_id}
```

The upload response should not grant broad bucket access. Use a short-lived,
object-specific signed URL or proxy the upload through a controlled endpoint.

### 8.5 Quizzes and attempts

```text
GET    /api/v1/quizzes
GET    /api/v1/quizzes/{quiz_id}
POST   /api/v1/quizzes/{quiz_id}/attempts
GET    /api/v1/attempts/{attempt_id}
PUT    /api/v1/attempts/{attempt_id}/answers
POST   /api/v1/attempts/{attempt_id}/submit
GET    /api/v1/attempts/{attempt_id}/result
GET    /api/v1/attempts/{attempt_id}/feedback
```

The quiz detail response must never include answer keys. The submission
endpoint must reject attempts outside the availability or attempt policy.

### 8.6 Progress and leaderboard

```text
GET    /api/v1/progress/me
GET    /api/v1/progress/me/subjects
GET    /api/v1/leaderboards/current
GET    /api/v1/leaderboards/weeks/{week_start}
GET    /api/v1/leaderboards/current/me
```

Paginate historical entries. Do not calculate a full leaderboard on every
student request.

### 8.7 Public endpoint behavior

Every endpoint must document:

- Authentication requirement
- Required role or ownership rule
- Request schema
- Response schema
- Status codes
- Error codes
- Pagination and sorting behavior
- Rate limit category
- Idempotency requirements

---

## 9. Backend-to-AI contract

### 9.1 Responsibilities

The backend:

- Authenticates the student.
- Checks entitlement and backend rate limits.
- Resolves the selected teacher and subject.
- Selects the allowed AI operation and budget.
- Sends minimal, authorized context.
- Persists the request and result metadata.
- Owns user-visible message status.

The AI service:

- Validates the internal request.
- Runs LangGraph and retrieval.
- Selects an approved model policy.
- Calls OpenRouter or voice providers.
- Applies prompt, safety, and output policies.
- Returns provider-independent structured results.

### 9.2 Internal request

Conceptually:

```json
{
  "contract_version": "2026-01",
  "request_id": "req_01...",
  "idempotency_key": "chat_01...",
  "operation": "tutor_chat",
  "user_ref": "usr_opaque",
  "conversation_ref": "conv_opaque",
  "teacher_bot_id": "teacher_math",
  "subject_id": "subject_math",
  "student_context": {
    "grade_level": "8",
    "language": "en",
    "learning_preferences": ["step_by_step"]
  },
  "messages": [
    {
      "role": "user",
      "content": "Explain fractions",
      "created_at": "2026-11-07T17:30:00Z"
    }
  ],
  "limits": {
    "max_output_tokens": 700,
    "deadline_ms": 20000
  },
  "policy_versions": {
    "safety": "1",
    "teacher": "math-3",
    "retrieval": "2"
  }
}
```

Do not send authentication cookies, password data, unnecessary profile
fields, or unrestricted conversation history.

### 9.3 Internal response

```json
{
  "contract_version": "2026-01",
  "run_id": "run_01...",
  "status": "completed",
  "content": {
    "text": "Fractions represent...",
    "format": "markdown"
  },
  "citations": [],
  "safety": {
    "status": "allowed",
    "flags": []
  },
  "usage": {
    "input_tokens": 420,
    "output_tokens": 180,
    "estimated_cost": 0.0012
  },
  "model": {
    "logical_route": "tutoring_standard"
  }
}
```

The AI service should not need to expose raw provider details to the
frontend. The backend may store provider metadata privately for operations.

### 9.4 Streaming

For streaming:

1. The backend creates a pending assistant message.
2. The backend opens an authenticated stream to the AI service.
3. The backend forwards validated deltas to the frontend.
4. The backend persists the completed content and terminal status.
5. On cancellation or provider failure, the backend persists an interrupted
   or failed status and emits a safe terminal event.

A stream is not complete until the terminal event is received or the backend
explicitly records a failure.

### 9.5 AI error mapping

Map internal errors to stable backend codes:

```text
AI_TIMEOUT              -> temporary retry message
AI_RATE_LIMITED         -> usage limit or retry-later message
AI_UNAVAILABLE           -> service unavailable message
AI_OUTPUT_INVALID        -> safe generation failure
AI_POLICY_BLOCKED        -> policy-safe response
AI_CONTEXT_TOO_LARGE     -> request-too-large response
```

Do not expose OpenRouter response bodies, API keys, hidden prompts, or
provider-specific stack traces.

---

## 10. Authentication and authorization

### 10.1 Recommended browser session design

For a browser-first Next.js application:

- Use a secure, HTTP-only session or refresh cookie.
- Use `Secure` in staging and production.
- Use an explicit `SameSite` policy compatible with the deployment topology.
- Scope cookies to the intended domain.
- Rotate sessions after login and privilege changes.
- Revoke sessions on logout and security events.
- Add CSRF protection for cookie-authenticated state-changing requests.

If frontend and backend are on different sites, design CORS, cookie, CSRF,
and trusted origins together before implementation.

### 10.2 Authentication dependency

`app/api/deps.py` should expose reusable dependencies for:

- Current authenticated user
- Required role
- Current student
- Current admin or content manager
- Internal service authentication
- Request ID
- Database session
- Idempotency key

Dependencies authenticate and load context. They should not perform unrelated
business mutations.

### 10.3 Authorization model

Use defense in depth:

1. Route-level authentication.
2. Role or capability check.
3. Object ownership or organization scope.
4. Service-level invariant check.
5. Repository query filter.

Examples:

- A student can read only their own private conversations.
- A student can submit only their own active attempt.
- A content manager can publish content but cannot change user roles.
- An administrator can manage teacher visibility only with audit logging.
- A worker can process a job only after verifying its job type and status.

Never rely only on a frontend-hidden button for authorization.

---

## 11. Caching, rate limits, and idempotency

### 11.1 Redis key policy

Use:

```text
gurukul:{env}:cache:catalog:{version}
gurukul:{env}:ratelimit:user:{user_id}:{operation}:{window}
gurukul:{env}:idempotency:{scope}:{key}
gurukul:{env}:lock:leaderboard:{week_start}
gurukul:{env}:job:{job_id}:status
gurukul:{env}:stream:{run_id}
```

Every key must have:

- An owner module
- A documented TTL
- A maximum value size
- A behavior if Redis is unavailable

### 11.2 What may be cached

Good candidates:

- Published subjects
- Enabled teacher-bot catalog data
- Course and lesson summaries
- Leaderboard snapshots
- Short-lived permission or entitlement reads
- Idempotency results

Do not cache private data under a key that omits the user or authorization
scope. Do not make Redis the only copy of scores, attempts, or messages.

### 11.3 Rate limits

Apply separate limits for:

- Registration and login
- Password reset
- Catalog reads
- Chat submissions
- Voice uploads and processing
- Quiz submissions
- Admin mutations
- WebSocket connections

Use atomic Redis operations and return a stable error with `Retry-After` when
possible. Rate limits are an abuse control, not a substitute for entitlement
and token-budget controls in the AI service.

### 11.4 Idempotency

Require idempotency keys for:

- Registration retries where duplicate creation is possible
- Message creation
- Voice job creation
- Attempt submission
- Payment or entitlement changes if introduced
- Admin publication actions

Store a request fingerprint and final response reference. A repeated identical
request returns the original result. A reused key with different input returns
`IDEMPOTENCY_KEY_REUSED`.

---

## 12. Background jobs and scheduling

### 12.1 Job requirements

Every job should define:

- Job name and version
- Payload schema
- Maximum attempts
- Retryable error classes
- Backoff strategy
- Visibility timeout
- Idempotency strategy
- Dead-letter behavior
- Metrics and logs

### 12.2 Job categories

Interactive follow-up:

- AI quiz feedback
- Email or notification delivery
- Voice status processing

Batch:

- Document-ingestion coordination
- Embedding-status updates
- Weekly leaderboard finalization
- Progress aggregation
- Retention cleanup
- Analytics exports

### 12.3 Weekly leaderboard finalization

The job should:

1. Determine the closed week in UTC.
2. Acquire a Redis or database lock.
3. Verify that no earlier finalization is incomplete.
4. Read durable weekly score components.
5. Apply the versioned ranking and tie-break rules.
6. Write a snapshot transactionally.
7. Publish a completion event through the outbox.
8. Release the lock.
9. Emit metrics and an audit record.

Rerunning the job must produce the same result for the same immutable input
and calculation version.

---

## 13. Error handling and reliability

### 13.1 Error classes

Use explicit categories:

```text
ValidationError
AuthenticationError
AuthorizationError
NotFoundError
ConflictError
RateLimitError
DependencyUnavailableError
DependencyTimeoutError
DomainStateError
InternalError
```

Each public error should include a stable code and request ID. Client
messages must be useful but must not disclose internal implementation details.

### 13.2 External dependency policy

For PostgreSQL, Redis, AI, object storage, and email:

- Set explicit connect and operation timeouts.
- Retry only operations known to be safe and transient.
- Use exponential backoff with a maximum.
- Add circuit-breaker behavior for repeated provider failures.
- Record dependency health and latency.
- Return a clear degraded response rather than hanging requests.

Do not use broad exception catches that convert failures into successful empty
responses.

### 13.3 Transaction policy

Use one transaction for state that must change atomically:

- User and student profile creation
- Attempt submission and objective scoring
- Weekly leaderboard snapshot creation
- Admin publication and outbox event creation
- Idempotency reservation and durable mutation when required

External calls should generally happen outside a database transaction unless
the operation is deliberately designed for that tradeoff. Use pending states,
outbox events, and workers to bridge database and external systems.

---

## 14. Security and privacy implementation

### 14.1 Secrets

Store secrets in the hosting provider's secret manager:

- Session/signing keys
- Database and Redis credentials
- AI service authentication keys
- Object-storage credentials
- Email provider credentials
- Telemetry credentials

Rotate secrets without rebuilding source code where possible.

### 14.2 Input validation

Validate:

- String length and encoding
- HTML/markdown policy
- File size, MIME type, extension, and duration
- Pagination limits
- Sort fields through an allowlist
- IDs and ownership
- Quiz answer shape
- WebSocket message size

Do not pass raw user-controlled sort columns, SQL fragments, URLs, or provider
model names into downstream operations.

### 14.3 Upload security

For documents and audio:

1. Authorize the upload request.
2. Issue a short-lived object-specific upload permission.
3. Enforce size and content-type limits.
4. Verify object metadata after upload.
5. Scan or quarantine where required.
6. Store only approved object references.
7. Queue processing.
8. Delete temporary files according to retention policy.

### 14.4 Audit logging

Audit:

- Login failures and security changes
- Role and permission changes
- Admin content publication
- Quiz publication and score overrides
- Data export and deletion
- Access to sensitive operational actions

Audit records should include actor, action, resource type and ID, outcome,
request ID, timestamp, and safe metadata. Never store passwords or bearer
tokens in audit logs.

---

## 15. Performance and database optimization

### 15.1 Query standards

- Select only required columns for list endpoints.
- Paginate all potentially unbounded lists.
- Use cursor pagination for high-volume messages or events.
- Index foreign keys and common filter combinations.
- Measure query plans before adding indexes.
- Avoid loading full conversation history for every AI request.
- Use materialized progress and leaderboard data.
- Set database statement timeouts.

### 15.2 Connection pooling

Tune pool size based on:

```text
total_connections =
  api_instances * api_pool_size
  + worker_instances * worker_pool_size
  + migration/admin connections
```

Keep the total below the PostgreSQL service limit with headroom. More
connections do not automatically mean more throughput.

### 15.3 Caching strategy

Use cache-aside for catalog and leaderboard reads:

1. Read cache.
2. On miss, query PostgreSQL.
3. Store the bounded result with a TTL.
4. Invalidate or version the key after a publication or snapshot update.

Never allow stale cache data to override authorization or durable scoring.

### 15.4 Streaming and large responses

Stream chat deltas rather than building oversized responses in memory. Put
limits on message size, result size, and concurrent streams per user.

---

## 16. Testing strategy

### 16.1 Unit tests

Test without network or database where possible:

- Password and session policies
- Authorization rules
- Quiz scoring and tie-breaking
- Attempt state transitions
- Entitlement and usage decisions
- Pagination and sorting validation
- Idempotency behavior
- Error mapping
- Leaderboard calculation
- Event schema validation

### 16.2 API tests

Use FastAPI's test transport to test:

- Request validation
- Authentication dependencies
- Permission failures
- Response schemas
- Error envelopes
- Pagination
- Idempotency
- CORS and security headers where applicable

### 16.3 Integration tests

Run against real disposable PostgreSQL and Redis instances:

- Migrations from an empty database
- Registration transaction
- Chat persistence
- Attempt submission and scoring
- Outbox delivery
- Leaderboard finalization
- Cache invalidation
- Worker retry and idempotency

Mock only external AI and provider boundaries in most backend integration
tests. Maintain a small set of contract tests against a test AI service.

### 16.4 Contract tests

Check:

- Generated frontend types match the committed backend OpenAPI artifact.
- Backend internal AI schemas match the AI repository's contract fixtures.
- Event payloads validate against their versioned schemas.
- Streaming messages have valid envelopes and terminal states.

### 16.5 Security tests

Include:

- Cross-user object access attempts
- Role escalation attempts
- CSRF behavior for cookie sessions
- Rate-limit enforcement
- Oversized input and uploads
- Sensitive-field redaction
- Invalid signatures and expired service requests
- SQL injection and unsafe query parameter tests

### 16.6 Required test cases

At minimum:

1. A student cannot read another student's conversation.
2. A student cannot see quiz answer keys.
3. A client cannot submit a score directly.
4. Repeated message submission with the same idempotency key does not create
   duplicate messages.
5. Reusing an idempotency key with a different body fails.
6. A failed AI call leaves an explicit failed message state.
7. A retryable AI call does not create duplicate durable results.
8. A leaderboard rerun is deterministic.
9. An expired quiz cannot accept an attempt.
10. A deleted or suspended user cannot authenticate or access data.

---

## 17. Local development

### 17.1 Local services

Use Docker Compose for:

- PostgreSQL with required extensions
- Redis
- S3-compatible object storage such as MinIO
- Optional local telemetry components

The AI service may run separately or be replaced by a contract-test stub.

### 17.2 Local startup sequence

```text
1. Copy .env.example to a local environment file.
2. Start PostgreSQL, Redis, and object storage.
3. Install locked Python dependencies.
4. Run database migrations.
5. Seed safe development catalog data.
6. Start the FastAPI API with reload enabled.
7. Start the worker process separately.
8. Run targeted tests and inspect OpenAPI.
```

Never use production credentials or production student data locally.

### 17.3 Development seed data

Seeds may include:

- Mathematics, Science, and English subjects
- Test teacher-bot catalog entries
- A development administrator
- A sample published quiz

Seed data must be environment-scoped and must not run automatically against
production.

---

## 18. Deployment architecture

### 18.1 Recommended first production topology

```text
CDN/WAF
  |
  +--> Next.js frontend
  |
  +--> FastAPI API containers
          |
          +--> Managed PostgreSQL
          +--> Managed Redis
          +--> Private object storage
          +--> Private AI service
          +--> Queue/worker containers
```

Use a managed container platform first unless the team already operates
Kubernetes. Kubernetes is not required for a reliable initial release.

### 18.2 API process

Run multiple stateless API instances behind a load balancer. The API process
must not depend on local disk for durable state. Local temporary files must
have bounded size and cleanup behavior.

The ASGI server should be configured with:

- Multiple workers only when container CPU/memory sizing supports them.
- Request and keep-alive timeouts.
- Graceful shutdown.
- Proxy header handling only for trusted proxies.
- A health endpoint that does not reveal secrets.

### 18.3 Worker process

Deploy workers separately so AI follow-up, voice, ingestion, and leaderboard
jobs can scale independently from HTTP traffic. Give workers only the
permissions and network access they need.

### 18.4 Database deployment

- Use managed PostgreSQL with automated backups.
- Enable TLS.
- Run migrations as an explicit release step.
- Use a restricted application role.
- Use a separate migration role where practical.
- Monitor connections, CPU, storage, locks, and slow queries.
- Test point-in-time recovery.

### 18.5 Redis deployment

- Use managed Redis with TLS and authentication.
- Configure memory limits and eviction policy intentionally.
- Monitor evictions, latency, connections, and fragmentation.
- Do not place durable learning records only in Redis.
- Use separate logical namespaces or instances for cache and queues if
  operational isolation requires it.

### 18.6 Object storage

Create separate buckets or prefixes for:

- User uploads
- Processed educational documents
- Voice input
- Generated audio
- Exports

Keep buckets private. Use signed URLs, lifecycle rules, encryption, and
access logs where required.

### 18.7 Network security

- Only the load balancer and required public endpoints have public ingress.
- PostgreSQL and Redis are private.
- AI service ingress accepts only authenticated backend traffic.
- Workers have no public ingress unless explicitly required.
- Use security groups or network policies to restrict east-west traffic.

---

## 19. Containerization

### 19.1 `Dockerfile`

The API image should:

1. Start from a supported minimal Python base image.
2. Install locked dependencies.
3. Copy application source.
4. Run as a non-root user.
5. Set a production-safe working directory.
6. Expose only the API port.
7. Use an explicit ASGI command.
8. Avoid development reload mode.

Do not bake secrets into the image.

### 19.2 `Dockerfile.worker`

Use the same dependency base where possible, but run the worker entry point.
Keep API and worker images separate if their startup or security needs differ.

### 19.3 Health endpoints

Provide:

```text
GET /health/live
GET /health/ready
```

`live` should indicate that the process is running. `ready` should verify
required dependencies enough to prevent traffic from reaching an unusable
instance, without creating expensive or mutating checks.

---

## 20. CI/CD pipeline

### 20.1 Pull request checks

Run:

1. Lockfile consistency.
2. Ruff format and lint.
3. Type checking.
4. Unit tests.
5. API and contract tests.
6. Migration validation.
7. Dependency vulnerability scan.
8. Secret scan.
9. Container build validation.

### 20.2 Staging deployment

After merge:

1. Build an immutable image tagged by commit SHA.
2. Push it to a private registry.
3. Run migrations against staging.
4. Deploy API and workers.
5. Run smoke tests.
6. Validate `/health/ready`.
7. Run frontend-backend and backend-AI contract tests.

### 20.3 Production deployment

Promote the exact tested image:

1. Confirm backups and migration compatibility.
2. Apply backward-compatible migrations.
3. Deploy API with rolling or blue-green strategy.
4. Deploy workers.
5. Run smoke tests.
6. Monitor error rate, latency, queue depth, and AI dependency health.
7. Roll back the application image if necessary.

Do not automatically roll back a database migration unless the migration
procedure was explicitly designed and tested for rollback.

### 20.4 Migration compatibility

Prefer expand-and-contract:

```text
1. Add nullable column or new table.
2. Deploy code that writes old and new representations.
3. Backfill in controlled batches.
4. Deploy code that reads the new representation.
5. Remove old representation only after all versions are compatible.
```

---

## 21. Observability

### 21.1 Request correlation

Accept or generate a safe request ID. Propagate it through:

```text
frontend -> backend -> AI service -> workers -> database/outbox events
```

Do not trust an arbitrary incoming ID without validation and length limits.

### 21.2 Metrics

Track:

- Request count, status, and latency by route
- Authentication success and failure
- Database pool and query latency
- Redis latency and errors
- AI request count, latency, status, and timeout rate
- Token and estimated-cost metadata received from AI
- Active streams and disconnects
- Queue depth, job age, retry count, and dead letters
- Quiz submissions and scoring failures
- Leaderboard finalization success
- Upload volume and processing failures

### 21.3 Logs

Use structured logs with:

```text
timestamp
level
service
environment
request_id
trace_id
route
user_ref
status_code
duration_ms
error_code
```

Never log passwords, cookies, authorization headers, provider API keys, raw
audio, or unrestricted student message content.

### 21.4 Alerts

Alert on:

- Sustained 5xx increases
- Authentication abuse
- Database pool exhaustion
- Redis failures or memory pressure
- AI timeout and failure spikes
- Queue backlog or dead-letter growth
- Failed migrations
- Leaderboard finalization failure
- Unexpected cost or usage growth

---

## 22. Data retention and privacy operations

Define retention by data type before production:

| Data | Example policy decision |
|---|---|
| Login/session records | Short operational retention |
| Chat messages | User-visible retention with deletion workflow |
| Raw voice input | Minimal retention or immediate deletion |
| Generated audio | Short TTL unless user saves it |
| Quiz attempts | Durable while needed for progress and ranking |
| Audit records | Longer restricted retention |
| AI usage metadata | Retain for cost and support analysis |
| Temporary uploads | Delete after processing or failure window |

Implement:

- Account deletion workflow
- Data export workflow
- Conversation deletion
- Audio deletion
- Consent version tracking
- Admin access auditing
- Background retention jobs

Deletion must account for PostgreSQL, Redis, object storage, logs, traces,
search/vector metadata, and backups according to the applicable policy.

---

## 23. Operational runbooks to write

Before production, create internal runbooks for:

1. Database connection exhaustion
2. Redis outage
3. AI service outage
4. OpenRouter provider degradation
5. Queue backlog
6. Failed leaderboard finalization
7. Accidental quiz publication
8. Suspicious account activity
9. Object-storage upload abuse
10. Data deletion request
11. Database restore
12. Secret rotation
13. Bad deployment rollback

Each runbook should include detection, impact, immediate mitigation,
escalation owner, recovery steps, and post-incident checks.

---

## 24. Implementation sequence

### Step 1: Repository foundation

- Create the FastAPI project and `pyproject.toml`.
- Configure locked dependencies and quality tools.
- Add settings, logging, request IDs, application factory, and health routes.
- Add Docker Compose for local PostgreSQL and Redis.

### Step 2: Database foundation

- Add SQLAlchemy async session management.
- Add Alembic.
- Create identity, role, and student profile migrations.
- Add repository and service tests.

### Step 3: Authentication

- Implement registration, login, logout, current-user lookup, and session
  revocation.
- Add authentication and role dependencies.
- Add rate limits and audit records.

### Step 4: Catalog

- Add subjects and teacher-bot metadata.
- Add publication state and cache-aside reads.
- Add admin authorization and audit logging.

### Step 5: Conversations

- Add conversations and messages.
- Add idempotent message creation.
- Add the internal AI client contract.
- Persist pending, completed, interrupted, and failed states.

### Step 6: Quizzes and progress

- Add immutable quiz versions.
- Add attempts, answers, deterministic scoring, and progress events.
- Add leaderboard calculation and snapshots.

### Step 7: Workers and operations

- Add queue infrastructure and outbox processing.
- Add notifications, AI feedback, cleanup, and scheduled leaderboard jobs.
- Add metrics, tracing, alerts, and runbooks.

### Step 8: Voice and content

- Add private object storage and signed uploads.
- Add voice job coordination.
- Add content metadata and AI ingestion coordination.

### Step 9: Production hardening

- Complete contract, security, load, and recovery tests.
- Validate migrations and backups.
- Deploy staging and run smoke tests.
- Promote immutable artifacts to production.

---

## 25. Definition of done

The backend is ready for its first production release when:

- The API and worker processes deploy independently.
- All required settings are typed and production secrets are externalized.
- PostgreSQL migrations are reviewed, tested, and backward compatible.
- Authentication, sessions, roles, ownership, and admin permissions are
  enforced server-side.
- Public OpenAPI and internal AI contracts are versioned.
- Chat, voice, quiz, ranking, progress, and catalog flows have explicit
  state transitions.
- Quiz scores and leaderboard ranks are calculated server-side.
- OpenRouter is reachable only through the AI service.
- Redis is used only for temporary/derived state and safe coordination.
- AI calls have timeouts, idempotency, rate limits, and durable metadata.
- Uploads use private storage and short-lived authorization.
- Workers have retries, dead-letter handling, and idempotency.
- Logs, metrics, traces, and alerts are available without leaking sensitive
  student data.
- Account deletion, data retention, and audit workflows are implemented.
- Unit, integration, contract, security, and end-to-end tests pass.
- Backups have been restored successfully in a non-production environment.
- Staging smoke tests pass before every production promotion.
