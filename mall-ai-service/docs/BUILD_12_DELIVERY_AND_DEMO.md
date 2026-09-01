# Build 12: Docker Compose Delivery and Browser Demo

## Goal

Turn the existing AI customer-service workflow into a reproducible local
demonstration without claiming that it is a cloud production deployment.

## Deliberate Scope

The Compose stack contains only services required by the current customer
workflow:

```text
Vue/Nginx -> FastAPI -> mall-portal -> MySQL
                    -> Redis
mall-portal -> RabbitMQ and MongoDB
FastAPI -> DeepSeek and Gemini external APIs
```

RabbitMQ and MongoDB are existing `mall-portal` runtime dependencies. They do
not mean that this build implements AI message processing, multi-Agent
coordination, Elasticsearch, Kubernetes, or a cloud deployment.

## Files Added

- Root `docker-compose.yml` orchestrates the local services and health gates.
- Dockerfiles package the FastAPI service, production Vue bundle, and Java
  portal source build.
- `application-docker.yml` gives Java container-only hostnames and local demo
  credentials; development configuration remains unchanged.
- `GET /health/ready` verifies the durable conversation backend without probing
  model providers.
- `scripts/start-demo.ps1` starts the stack, waits for public health checks and
  can prepare disposable local accounts/orders plus two-account ownership
  verification.
- `scripts/stop-demo.ps1` stops the stack and requires an explicit typed
  confirmation before deleting local data volumes.

## Acceptance Criteria

1. `docker compose up --build -d` creates healthy MySQL, Redis, MongoDB,
   RabbitMQ, Java, FastAPI and Vue services.
2. Browser request `/api/*` reaches FastAPI through Nginx; the browser does not
   need a separate FastAPI address or raw Token input.
3. FastAPI readiness is `200` only when the configured Redis conversation store
   is reachable. It must not call an external model in a health probe.
4. `-PrepareDemoData` creates only local disposable accounts/orders, prints no
   Bearer Token, and then verifies login and cross-account order denial.
5. Browser demo follows this sequence: login -> query own logistics -> ask a
   policy question -> create a return proposal -> confirm once -> show the
   repeated/foreign-account denial boundary.

## Verification Status

### Static and Unit Verification

- Python unit suite: `106/106` passed, including readiness and public-stack
  verifier tests.
- Vue production build passed.
- Java portal source package passed with the Docker plugin skipped.
- Compose YAML, service-dependency contract and both PowerShell scripts passed
  static parsing checks.

The legacy Maven project binds an old remote Docker plugin to `package`. Local
source and container builds pass `-Ddocker.skip=true` so that stale remote host
configuration cannot replace the Compose-owned build path.

### Runtime Verification Completed on 2026-08-05

- Docker Compose created healthy MySQL, Redis, MongoDB, RabbitMQ, Java portal,
  FastAPI and Vue/Nginx services on this local machine.
- Public endpoint checks passed for the Vue page (`5173`), FastAPI readiness
  (`8000`) and Java health endpoint (`8085`).
- Disposable local accounts and independent orders were created. The live
  verification confirmed that each account can read its own order, cannot read
  the other account's order, and that missing or invalid Bearer Tokens are
  rejected.
- A real browser-contract request passed through FastAPI to the live RAG path:
  the quality-return shipping question produced a grounded answer; source
  metadata remained server-side.
- The reviewed live grounding runner passed all `15/15` hard contracts using
  the project-owned demo corpus. This includes 12 supported policy questions
  and 3 no-evidence refusal cases. It is small local evaluation evidence, not a
  general or production-accuracy claim.

Two startup defects were discovered only through real runtime verification and
then fixed: the MySQL health check no longer accepts its temporary import
server as ready, and the AI container uses Docker's host gateway for a
host-only Gemini VPN proxy. The demo startup script also pre-pulls missing base
images before building so BuildKit does not independently fail on remote image
metadata requests.

### Still Pending: Human Browser Click-through

The browser page is reachable, but Build 12 is deliberately not marked fully
complete until the learner performs the visible login, policy-answer, return
proposal/confirmation, and cross-account-denial flow below. This keeps the
record honest: service-level verification is complete; the final product-demo
walkthrough still needs user-facing evidence.

## Browser Acceptance Script

After Docker Desktop is available, run:

```powershell
.\scripts\start-demo.ps1 -PrepareDemoData
```

Then perform this browser-only demonstration at `http://127.0.0.1:5173`:

1. Open the login panel and sign in as Account A using the one-time password
   entered into the setup script.
2. Send a logistics request with Account A's printed order number. Confirm that
   the answer contains a server-verified fact card rather than an invented
   logistics result.
3. Ask a reviewed policy question such as `退货运费由谁承担？`. Confirm that the
   response shows the customer answer and does not expose RAG source metadata.
4. Start a return request for Account A's own order. Supply any requested
   product/reason information, review the proposal and use the visible confirm
   action exactly once.
5. Start a new browser session, sign in as Account B, and request Account A's
   order number. Confirm that the system does not reveal Account A's order or
   permit a write.

The first three steps are repeatable presentation evidence. The return path is
the flagship evidence: natural language -> Java ownership verification -> RAG
policy evidence -> proposal -> explicit confirmation -> Java-side write guard.

## Known Local Constraints

- External model keys are read at runtime from `mall-ai-service/.env`; they are
  not copied into images.
- Historical note: this Build 12 environment used Gemini Embedding and a Docker
  VPN/proxy route. Build 16.5 replaced that runtime path with the packaged local
  BGE model after measured comparison, then removed the Gemini configuration and
  old collection. This note is retained only to explain older demo evidence.
- The MySQL import is demo data. `-RemoveDemoData` deletes only named Compose
  volumes after an explicit confirmation; it does not touch a separately
  installed local MySQL service.
- Image builds may download Maven, Python and Node dependencies on first run.
- This build is a reproducible local demo, not remote-server deployment,
  autoscaling, monitoring platform, or production high-availability evidence.
