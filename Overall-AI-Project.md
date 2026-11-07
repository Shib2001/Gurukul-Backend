# Gurukul - Overall AI Project Architecture

## 1. Document purpose

This document is the system-design blueprint for **Gurukul**, an AI-powered
learning platform. It defines how the frontend, backend, AI services, data
stores, real-time features, and production infrastructure work together.

The project is intentionally split into three repositories:

1. `gurukul-frontend` - the student, teacher/admin, and operations web
   application.
2. `gurukul-backend` - the authoritative product API, authentication,
   persistence, quiz and ranking logic, and integration gateway.
3. `gurukul-ai` - AI teachers, retrieval-augmented generation, voice
   orchestration, prompt policies, and model routing.

The repositories should be independently deployable, but they must follow
versioned contracts and shared security conventions.

This document describes the target architecture. The detailed implementation
documents should refine it:

- `Frontend.md` - routes, components, frontend dependencies, optimization,
  and frontend deployment.
- `Backend.md` - API routes, database tables, backend dependencies,
  optimization, and backend deployment.
- `AI.md` - agents, prompts, RAG, voice, token controls, and AI deployment.

---

## 2. Product vision and core principles

Gurukul should feel like a digital school rather than a generic chatbot
application. Each student should be able to learn from subject-specific
teachers, practice with quizzes, receive useful feedback, and understand their
progress over time.

### Core capabilities

- Student registration, login, profile, and learning preferences
- Subject-specific AI teachers, such as Mathematics, Science, and English
  Literature
- Text chat and voice-based learning sessions
- Retrieval from approved educational content
- Explanations adapted to the student's level
- Weekly quizzes, attempts, scoring, and feedback
- Weekly rankings and personal progress history
- Administrative content and teacher-bot configuration
- Usage limits, moderation, analytics, and operational monitoring

### Architectural principles

1. **Backend is the system of record.** The browser must not directly write
   to PostgreSQL, Redis, object storage, or vector storage.
2. **AI is a controlled service, not an authority.** AI may propose answers,
   explanations, quiz questions, and feedback, but the backend controls
   identity, permissions, quiz scoring, ranking, and durable records.
3. **Every service has a clear ownership boundary.** A service may read
   another service through an API or event contract, but it must not reach
   into another service's private database tables.
4. **Async by default for expensive work.** Embeddings, document ingestion,
   audio transcription, text-to-speech, analytics, and notifications should
   use workers and queues where latency does not need to be interactive.
5. **Safe educational behavior.** Responses should be grounded where
   possible, identify uncertainty, avoid fabricated citations, and use
   age-appropriate explanations.
6. **Design for observability.** Every request and AI run needs a correlation
   ID, timing data, outcome, and cost/usage metadata.
7. **Privacy by default.** Collect only the data needed for learning,
   security, billing, and product improvement. Voice data requires explicit
   policy and retention controls.
8. **Contracts before coupling.** API schemas, event schemas, and error
   formats must be versioned and tested.

---

## 3. High-level architecture

```text
                                    +----------------------+
                                    |  Admin / Operations   |
                                    |  Web interface       |
                                    +----------+-----------+
                                               |
+------------------+       HTTPS/WebSocket      v
| Student Browser  | <--------------------> +----------------------+
| Next.js Web App  |                         | FastAPI Backend      |
+------------------+                         | Auth/API/Domain      |
                                             +----+----+------+------+
                                                  |    |      |
                                      SQL/Cache    |    |      | Events/jobs
                                                  v    v      v
                                           +------+  +---+  +----------+
                                           |Postgres|  |Redis| |Queue/   |
                                           |primary |  |     | |Workers  |
                                           +---+----+  +---+  +----------+
                                               |          |
                                               |          +----------------+
                                               |                           |
                                               v                           v
                                      +----------------+          +----------------+
                                      | Object Storage |          | AI Service     |
                                      | files/audio    | <-------> | LangGraph/API  |
                                      +----------------+  HTTPS    | RAG/Voice      |
                                                                    +----+-----------+
                                                                         |
                                                   +---------------------+----------------+
                                                   |                                      |
                                                   v                                      v
                                           +---------------+                      +---------------+
                                           | Vector Store  |                      | Model/Voice   |
                                           | embeddings    |                      | providers     |
                                           +---------------+                      +---------------+
```

### Service responsibilities

| Component | Owns | Must not own |
|---|---|---|
| Frontend | UI state, rendering, client-side validation, accessibility, API consumption | Authorization decisions, quiz score authority, provider secrets |
| Backend | Users, roles, courses, quiz definitions, attempts, scores, rankings, entitlements, audit records | Prompt internals and direct model-provider orchestration |
| AI service | Agent graphs, prompts, retrieval, model routing, transcription/TTS orchestration, AI-run metadata | User authorization, authoritative scores, final ranking |
| PostgreSQL | Durable relational product data and transactional consistency | Ephemeral cache or model context |
| Redis | Cache, rate limits, short-lived sessions, idempotency, job coordination | Sole source of durable student progress |
| Vector store | Chunk embeddings and retrieval metadata | User accounts, permissions, quiz scores |
| Object storage | Documents, permitted audio, exports, and other large blobs | Frequently changing application state |
| Queue/workers | Deferred and retryable jobs | Synchronous authorization or ranking decisions |

---

## 4. Repository and ownership model

### 4.1 `gurukul-frontend`

Recommended top-level areas:

```text
app/                 Next.js routes and layouts
components/          Reusable UI components
features/            Subject, chat, quiz, ranking, profile features
lib/                 API client, auth client, telemetry, validation
hooks/               Shared client hooks
styles/              Design tokens and global styles
tests/               Unit, integration, and browser tests
```

The frontend communicates with the backend only through the public API and
real-time endpoints. It never contains OpenRouter, database, Redis, or
service credentials.

### 4.2 `gurukul-backend`

Recommended top-level areas:

```text
app/
  api/                Versioned HTTP and WebSocket endpoints
  core/               Settings, security, logging, lifecycle
  db/                 Sessions, migrations, repositories
  models/             Persistence models
  schemas/            Request and response contracts
  services/           Domain services and integrations
  workers/            Queue consumers and scheduled jobs
tests/
```

The backend exposes a stable API, validates all input, enforces permissions,
coordinates AI calls, and persists product outcomes.

### 4.3 `gurukul-ai`

Recommended top-level areas:

```text
app/
  agents/             LangGraph graphs and state
  prompts/            Versioned system prompts
  retrieval/          Ingestion, chunking, embeddings, filters
  providers/          Model, transcription, and TTS adapters
  policies/           Safety, output validation, budgets
  api/                Internal AI endpoints
  workers/            Ingestion and asynchronous AI jobs
tests/
```

The AI repository exposes internal, authenticated endpoints. The public
browser must never call the AI service directly.

### 4.4 Shared contracts

Avoid a shared runtime package that forces all repositories to release
together. Instead, use:

- OpenAPI for backend HTTP contracts
- JSON Schema or generated types for event payloads
- A documented WebSocket message protocol
- Versioned contract fixtures tested in CI
- Generated frontend API types from a pinned backend OpenAPI document

Breaking changes require a new API version or a compatibility period.

---

## 5. Main user journeys

### 5.1 Registration and login

1. The student opens the frontend.
2. The frontend submits registration data to `POST /api/v1/auth/register`.
3. The backend validates the request, hashes the password if local auth is
   enabled, creates the user and student profile in one transaction, and
   returns a session or token pair.
4. The frontend stores credentials using the selected secure session pattern.
   Prefer an HTTP-only, secure, same-site cookie for browser sessions.
5. The backend emits an audit event and optionally queues a welcome
   notification.

Social login can be added later through an identity provider. It should map to
the same internal user model rather than create a separate account system.

### 5.2 Text lesson with an AI teacher

1. The student selects a subject and teacher from the frontend.
2. The frontend sends a message and a client-generated idempotency key to the
   backend.
3. The backend authenticates the student, checks access and usage limits,
   creates a conversation message, and calls the internal AI service.
4. The backend passes a minimized context package:
   - authenticated student ID or an internal opaque identifier
   - subject and teacher ID
   - student level and learning preferences
   - conversation context or a bounded summary
   - request ID and policy version
5. The AI service runs the selected graph:
   - validates the request
   - applies the teacher system prompt
   - retrieves approved content when appropriate
   - routes to a model
   - validates the output
   - returns answer, citations, usage, and safety metadata
6. The backend persists the assistant message and AI-run metadata.
7. The frontend renders the response and any citations or follow-up actions.

The backend should support streaming tokens for a responsive UI, but the
final assistant message must be persisted only after the stream completes or
is explicitly marked interrupted.

### 5.3 Voice lesson

For the first production version, use a controlled turn-based flow:

1. The frontend requests a short-lived upload or session authorization from
   the backend.
2. Audio is sent through the backend-controlled path or an authorized
   object-storage upload.
3. The AI service transcribes audio, applies the same teacher and safety
   policies as text chat, generates a response, and synthesizes speech.
4. The backend records the transcript and references the generated audio.
5. The frontend receives status updates and plays the response.

Streaming speech-to-speech can be introduced later, but it requires stricter
connection lifecycle, interruption, moderation, and cost controls.

### 5.4 Weekly quiz and ranking

1. The backend publishes or activates a quiz with a fixed version and
   availability window.
2. The student requests the quiz. The backend returns questions without
   answer keys.
3. The student submits answers. The backend validates the attempt and scores
   objective questions authoritatively.
4. Subjective answers may receive AI feedback, but ranking points must use a
   deterministic, reviewed scoring policy.
5. At the end of the weekly window, a scheduled job finalizes the leaderboard
   snapshot.
6. The frontend reads the student's rank, score, percentile, and improvement
   from the backend.

Ranking must be computed from server-side records. A browser-provided score
must never be trusted.

---

## 6. API and communication boundaries

### 6.1 Public backend API

Use a versioned prefix such as `/api/v1`. Initial resource groups:

```text
/auth
/users
/students
/subjects
/teachers
/conversations
/messages
/voice
/quizzes
/attempts
/leaderboards
/progress
/notifications
/health
```

The detailed request and response definitions belong in `Backend.md`.

All responses should have a consistent error shape:

```json
{
  "error": {
    "code": "QUIZ_NOT_AVAILABLE",
    "message": "The quiz is not currently available.",
    "request_id": "req_01H..."
  }
}
```

Do not expose stack traces, provider errors, database details, prompt text, or
secrets in public errors.

### 6.2 Internal backend-to-AI API

The internal API should include endpoints conceptually similar to:

```text
POST /internal/v1/chat/runs
POST /internal/v1/voice/transcribe
POST /internal/v1/voice/synthesize
POST /internal/v1/quiz/feedback
POST /internal/v1/retrieval/query
GET  /internal/v1/health
```

Internal requests require service authentication, a timestamp or nonce, and a
request ID. The AI service must still validate authorization claims and
resource identifiers rather than trusting arbitrary caller input.

### 6.3 Events and asynchronous jobs

Use a Redis-backed queue initially if scale and operational simplicity justify
it. A managed message broker can replace it later without changing domain
contracts.

Example events:

```text
user.created
conversation.message.created
ai.run.completed
ai.run.failed
voice.transcription.completed
quiz.attempt.submitted
quiz.attempt.scored
leaderboard.week.finalized
content.ingestion.requested
```

Every event should include:

```json
{
  "event_id": "evt_01H...",
  "event_type": "quiz.attempt.submitted",
  "event_version": 1,
  "occurred_at": "2026-11-07T17:30:00Z",
  "request_id": "req_01H...",
  "producer": "gurukul-backend",
  "payload": {}
}
```

Consumers must be idempotent. Persist an event ID or use an idempotency key
before applying a side effect.

### 6.4 Real-time protocol

Use WebSockets or Server-Sent Events for:

- Streaming assistant responses
- Voice processing status
- Quiz submission status
- Notifications

The connection must authenticate during handshake, enforce per-user
connection limits, send heartbeats, and close cleanly on token expiry.

Example message envelope:

```json
{
  "type": "assistant.delta",
  "request_id": "req_01H...",
  "sequence": 12,
  "data": {
    "text": "..."
  }
}
```

The client must tolerate reconnects, duplicate messages, missing deltas, and
an explicit `completed` or `failed` terminal message.

---

## 7. Data architecture

### 7.1 PostgreSQL

PostgreSQL is the source of truth for relational product data. The initial
logical domains are:

**Identity and access**

- `users`
- `student_profiles`
- `roles`
- `user_roles`
- `sessions` or external identity mappings

**Learning catalog**

- `subjects`
- `teacher_bots`
- `courses`
- `lessons`
- `content_documents`
- `content_versions`

**Conversations**

- `conversations`
- `conversation_participants`
- `messages`
- `ai_runs`

**Assessment**

- `quizzes`
- `quiz_versions`
- `quiz_questions`
- `quiz_options`
- `quiz_attempts`
- `quiz_answers`
- `quiz_feedback`

**Progress and ranking**

- `student_progress`
- `learning_events`
- `weekly_scores`
- `leaderboard_snapshots`

**Operations**

- `subscriptions` or entitlements, if monetization is introduced
- `notifications`
- `audit_logs`
- `outbox_events`

Important modeling rules:

- Use UUID or another non-sequential public identifier.
- Store timestamps in UTC.
- Add `created_at` and `updated_at` to mutable entities.
- Keep quiz versions immutable after publication.
- Use unique constraints for one active attempt or one result where required.
- Index foreign keys and high-cardinality query fields.
- Use database transactions for registration, attempt submission, scoring, and
  leaderboard finalization.
- Use an outbox table when a database transaction must reliably publish an
  event.

### 7.2 Redis

Redis is for temporary or derived state:

- API and AI rate limits
- Short-lived session or login state
- Frequently accessed subject and teacher configuration
- Conversation stream coordination
- Idempotency keys
- Queue data and worker leases
- Temporary voice-processing status
- Leaderboard read cache
- Per-user and per-tenant AI budgets

Every key needs an owner, namespace, TTL policy, and maximum size. Redis loss
must not destroy student progress, quiz attempts, or ranking history.

Suggested key pattern:

```text
gurukul:{environment}:{domain}:{identifier}:{purpose}
```

### 7.3 Vector storage

Use a vector-capable store such as `pgvector` in PostgreSQL for the initial
version if the scale is moderate. This reduces operational complexity and
allows retrieval metadata to share transactions with content records.

Move to a dedicated vector service only when ingestion volume, query
throughput, or operational requirements justify it.

Each chunk should carry metadata such as:

```text
document_id
document_version
subject_id
grade_level
language
content_type
visibility
source
approved_at
```

Retrieval must filter by authorization and educational scope before or during
similarity search. Similarity alone is not an authorization mechanism.

### 7.4 Object storage

Use private object storage for:

- Uploaded educational documents
- Audio input and generated audio
- Data exports
- Large generated artifacts

Use short-lived signed URLs, encryption at rest, content-type and size
validation, malware scanning where applicable, and lifecycle deletion rules.
Store only object metadata and references in PostgreSQL.

### 7.5 Database ownership

The backend owns the application PostgreSQL schema. The AI service may own
AI-specific operational tables only if they cannot be represented through a
backend contract. Avoid giving the AI service unrestricted credentials to the
backend schema.

---

## 8. AI system design

### 8.1 Teacher-bot model

A teacher bot should be configuration plus a versioned prompt policy, not a
separate hard-coded application for each subject.

Example configuration:

```text
teacher_bot_id
subject_id
display_name
description
grade_range
supported_languages
prompt_version
retrieval_policy
model_policy
safety_policy
enabled
```

The graph should receive a normalized request and use the selected
configuration. Subject-specific differences should primarily live in
versioned prompt and retrieval configuration.

### 8.2 LangGraph flow

An interactive run can follow this controlled sequence:

```text
Input validation
    -> policy and entitlement check
    -> conversation summary/context selection
    -> retrieval decision
    -> filtered retrieval
    -> prompt assembly
    -> model routing
    -> output validation
    -> safety checks
    -> citation and usage metadata
    -> response
```

Every node should have timeouts, structured logs, and a defined failure path.
The graph should not retry unsafe or invalid output indefinitely.

### 8.3 RAG

RAG content must be curated, versioned, and traceable. The AI response should
return source references where retrieval was used. If no approved content is
found, the teacher should either answer from general knowledge with a clear
qualification or say that it cannot verify the requested detail.

Use:

- Chunking based on document structure rather than arbitrary token cuts
- Metadata filters for subject, grade, language, and publication status
- Hybrid retrieval when keyword precision matters
- Reranking only when its latency and cost are justified
- Bounded context windows
- Cached embeddings and repeated-query results

### 8.4 Model routing and budget controls

OpenRouter or another provider gateway should be called only by the AI
service. Provider keys must be stored in a secret manager, never in the
frontend or database.

Routing policy can select:

- A low-cost model for classification, summarization, and simple tutoring
- A stronger model for difficult explanations or quality-sensitive feedback
- A dedicated transcription model for voice input
- A dedicated TTS provider for speech output

Token protection should combine:

- Per-user request and token limits
- Per-plan or entitlement limits
- Per-model daily and monthly budgets
- Redis counters with atomic increments and TTLs
- Maximum input and output token limits
- Conversation summarization and context trimming
- Result caching for safe, deterministic operations
- Exponential backoff only for retryable provider failures
- Circuit breakers when a provider is degraded
- A fallback response or provider only when policy permits it

Usage must be recorded durably after a run, while Redis provides fast
admission control. A Redis counter is not the final billing or audit record.

### 8.5 AI safety and quality

Teacher prompts should define:

- Role and subject scope
- Target age or grade level
- Explanation style
- Socratic questioning behavior
- Rules for uncertainty and citations
- Prohibited content and escalation behavior
- Assessment integrity rules
- Language and accessibility behavior

Do not allow the model to reveal hidden prompts, internal policies, secrets,
other students' data, or retrieval documents outside the authorized scope.

Validate structured outputs with schemas. Store prompt, model, retrieval,
latency, token, and safety-policy versions in `ai_runs` for debugging and
evaluation, while avoiding unnecessary raw sensitive content.

---

## 9. Security, privacy, and trust

### Identity and access

- Use secure, HTTP-only cookies for browser sessions where practical.
- Hash passwords with a current adaptive password hash.
- Require verified email or another account-verification step if appropriate.
- Enforce role-based access control on the backend.
- Separate student, teacher/admin, content-manager, and operations privileges.
- Rotate signing keys and provider credentials.
- Expire refresh sessions and support revocation.

### API security

- Validate every request with typed schemas.
- Apply authentication before resource access.
- Enforce object-level authorization, not only route-level authorization.
- Rate-limit authentication, chat, voice, quiz submission, and admin routes.
- Use idempotency for retried writes.
- Restrict CORS to known frontend origins.
- Set security headers and enforce HTTPS.
- Redact tokens, passwords, audio contents, and sensitive payloads from logs.

### Student privacy

- Define what is stored for chat and voice and for how long.
- Provide deletion and export workflows where legally required.
- Avoid using student conversations for model training without explicit,
  informed consent and a separate data-governance process.
- Restrict access to minors' data and apply appropriate parental or
  institution policies for the target market.
- Encrypt data in transit and at rest.
- Maintain audit logs for privileged access.

### AI-specific threats

Protect against:

- Prompt injection in user messages and retrieved documents
- Data exfiltration through tool or retrieval calls
- Malicious or poisoned educational documents
- Excessive generation and denial-of-wallet attacks
- Cross-user conversation or cache leakage
- Unsafe educational or age-inappropriate responses

Treat retrieved documents and user text as untrusted input. Retrieval filters,
tool allowlists, output validation, and budget controls are required.

---

## 10. Performance and scalability

### Request path

- Keep synchronous API work short and bounded.
- Stream chat responses when useful, but persist a final result.
- Cache stable catalog data and teacher configuration.
- Paginate conversations, messages, rankings, and activity history.
- Use database connection pooling and query timeouts.
- Avoid N+1 queries with explicit loading or batch queries.

### Worker path

Move these operations to workers:

- Document parsing and embedding
- Audio transcription and TTS
- Long-running AI feedback
- Email and notifications
- Leaderboard finalization
- Analytics aggregation
- Cleanup and retention jobs

Workers need retry limits, dead-letter handling, idempotency, and metrics for
queue depth and job age.

### Scaling strategy

1. Start with separate frontend, backend, and AI deployments and managed
   PostgreSQL/Redis.
2. Scale backend API instances horizontally.
3. Scale AI workers separately from API workers.
4. Separate interactive and batch queues.
5. Add read replicas or partitioning only when measured workloads require it.
6. Introduce a dedicated vector store or message broker only with evidence.

Do not scale by increasing timeouts or adding retries without measuring the
underlying bottleneck.

---

## 11. Observability and operations

Use structured JSON logs and propagate:

```text
request_id
trace_id
user_id or opaque subject ID
service
route or job name
ai_run_id
model/provider
duration_ms
status
error_code
```

### Metrics

Track at minimum:

- HTTP request rate, latency, and error rate
- WebSocket connection count and disconnects
- Database pool usage and slow queries
- Redis latency, memory, evictions, and queue depth
- AI latency by model and teacher
- AI tokens and estimated cost
- Provider errors and fallback rate
- Retrieval hit rate and citation rate
- Voice transcription/TTS duration and failure rate
- Quiz submission errors
- Worker retries and dead-letter jobs
- Weekly active students and learning completion

### Tracing

Use distributed tracing across:

```text
frontend request
  -> backend request
  -> AI run
  -> retrieval
  -> model provider
  -> persistence/event
```

Never put raw passwords, access tokens, full voice recordings, or unrestricted
student messages into traces.

### Alerts

Alert on user-impacting symptoms:

- Elevated 5xx or authentication failures
- AI provider error or timeout spikes
- Queue backlog exceeding an SLO
- Database connection exhaustion
- Redis memory pressure
- Unexpected token-cost growth
- Ranking finalization failures
- Object-storage or voice-processing failures

---

## 12. Deployment architecture

### 12.1 Environments

Use at least:

- `development` - local Docker Compose and test providers
- `staging` - production-like managed dependencies and synthetic data
- `production` - isolated credentials, domains, and data

Never use production student data in development or staging.

### 12.2 Production components

A practical initial production deployment consists of:

```text
CDN / WAF
    -> Frontend hosting or Next.js container
    -> Backend API containers
    -> Backend worker containers
    -> AI API containers
    -> AI worker containers
    -> Managed PostgreSQL
    -> Managed Redis
    -> Private object storage
    -> Monitoring and secret manager
```

The frontend may use a managed Next.js platform or a container platform. The
backend and AI services can run on a managed container service initially.
Kubernetes is an option when the team has a real need for its operational
complexity; it should not be required for the first release.

### 12.3 Network boundaries

- Public internet reaches only the CDN/WAF and explicitly public frontend/API
  endpoints.
- PostgreSQL, Redis, and object storage remain private.
- AI API endpoints are private or protected by an API gateway and service
  authentication.
- Workers run without public ingress where possible.
- Administrative interfaces require stronger authentication and audit logging.

### 12.4 CI/CD

Each repository should have a pipeline that:

1. Installs pinned dependencies.
2. Runs formatting and lint checks.
3. Runs unit and integration tests.
4. Runs security and dependency checks.
5. Builds an immutable artifact.
6. Publishes an image or deployment artifact.
7. Deploys to staging.
8. Runs smoke and contract tests.
9. Promotes to production with approval or a controlled release policy.

Database migrations must run as an explicit, reviewed deployment step. Backward
compatible migrations should be used so old and new application versions can
coexist during rollout.

### 12.5 Secrets and configuration

Use a managed secret store for:

- Session/signing keys
- Database and Redis credentials
- OpenRouter and voice-provider keys
- Object-storage credentials
- Internal service authentication keys
- Monitoring credentials

Configuration should be injected at runtime. Do not commit `.env` files with
real values. Maintain an example configuration file with safe placeholders.

### 12.6 Backups and disaster recovery

- Enable automated PostgreSQL backups and point-in-time recovery.
- Test restoration, not merely backup creation.
- Define retention for object storage and database backups.
- Replicate critical data according to the required recovery objectives.
- Document recovery procedures and ownership.
- Treat Redis as rebuildable unless a feature explicitly requires durable
  Redis persistence.

Define targets before launch:

```text
RPO - maximum acceptable data loss
RTO - maximum acceptable recovery time
```

---

## 13. Testing strategy

### Unit tests

Test domain rules in isolation:

- Permission checks
- Quiz scoring
- Ranking calculations
- Usage-budget decisions
- Prompt selection and policy configuration
- Retrieval filters
- Serialization and validation

### Contract tests

Verify that:

- Frontend requests match backend OpenAPI schemas.
- Backend internal requests match AI schemas.
- Event producers and consumers agree on versions.
- Error responses remain compatible.

### Integration tests

Use disposable PostgreSQL, Redis, and object-storage-compatible services to
test registration, chat persistence, quiz submission, worker idempotency,
leaderboard finalization, and failure recovery.

### AI evaluation

Maintain a versioned evaluation set for each teacher bot. Measure:

- Factuality and citation correctness
- Educational usefulness
- Grade-level appropriateness
- Refusal and safety behavior
- Prompt-injection resistance
- Latency and token cost

Prompt or model changes should be evaluated before production promotion.

### End-to-end tests

Cover the critical student journeys:

1. Register and sign in.
2. Start a teacher conversation.
3. Receive a streamed response.
4. Complete and submit a quiz.
5. View the weekly ranking.
6. Recover from a provider or WebSocket failure.

---

## 14. Recommended release phases

### Phase 1 - Foundation

- Three repository skeletons
- Authentication and student profiles
- Subject and teacher catalog
- PostgreSQL migrations
- Basic chat through the backend and AI service
- Structured logs, request IDs, and CI

### Phase 2 - Learning loop

- Conversation history and summaries
- Curated content ingestion and RAG
- Quiz authoring, attempts, deterministic scoring
- Progress dashboard
- Weekly leaderboard snapshots

### Phase 3 - Voice and operations

- Turn-based voice input and output
- Usage budgets and detailed cost monitoring
- Admin content management
- Moderation and audit workflows
- Notifications and scheduled jobs

### Phase 4 - Scale and quality

- Streaming voice where justified
- Better model routing and evaluation automation
- Advanced analytics and recommendations
- Read replicas, queue separation, or dedicated vector infrastructure based
  on measured demand

---

## 15. Decisions to confirm before implementation

These choices affect the detailed repository designs and should be confirmed
before coding beyond the foundation:

1. Target age range and whether minors require parental or institution
   controls.
2. Initial countries, languages, and data-residency requirements.
3. Local authentication versus a managed identity provider.
4. Whether Gurukul is free, subscription-based, institution-based, or mixed.
5. Whether quizzes are authored by administrators, generated by AI and
   reviewed, or both.
6. Voice retention policy and whether raw audio may be stored.
7. Initial hosting provider and preferred managed services.
8. Whether `pgvector` is sufficient for the first release.
9. Required availability, RPO, RTO, and budget limits.
10. Whether real-time streaming is required in the first public release.

Until these decisions are made, the architecture should preserve replaceable
adapters for identity, model providers, voice providers, vector storage, and
hosting.

---

## 16. Definition of done for the first production release

The first release is ready only when:

- All three repositories build and deploy independently.
- API and event contracts are versioned and tested.
- Authentication and object-level authorization are implemented.
- Student progress and quiz scores are durable in PostgreSQL.
- AI calls are authenticated, rate-limited, budgeted, and observable.
- Retrieval is scoped to approved, authorized content.
- Prompt and model versions are recorded for AI runs.
- Voice processing has explicit retention and failure behavior.
- Leaderboards are computed server-side and finalized reproducibly.
- Backups have been restored successfully in a test.
- Staging smoke tests pass before production promotion.
- Critical student flows have end-to-end coverage.
- Security, privacy, incident response, and data-deletion procedures are
  documented.

