# Build 04 — Vue Customer-Service UI

## Goal

Create a focused Vue 3 client for the AI customer-service workflow. It is a
demonstration client for the existing mall Java + FastAPI architecture, not a
replacement for the full mall storefront.

## Why this batch exists

The workspace contains the Java mall services and the FastAPI AI service, but
does not contain the separate upstream Vue storefront source. A small,
purpose-built client gives the project a usable user-facing entry point without
pretending that a full storefront has been integrated.

## Technology

- Vue 3 + TypeScript + Vite
- Native `fetch`; no UI component library or unnecessary frontend framework
- Vite development proxy: `/api` -> FastAPI at `http://127.0.0.1:8000`
- A generated browser session ID for multi-turn conversation continuity
- A development-only Bearer Token field stored in `sessionStorage`; a future
  real mall login can supply the same header without changing the chat API

## Scope

1. Send `session_id` and user message to `POST /customer-service`.
2. Pass the local development Authorization header when configured.
3. Render natural-language answers plus verified fact cards, RAG sources,
   return-draft product choices, and an explicit confirmation action.
4. Build successfully with `npm run build`.

## Explicit non-goals

- No fake login, fake order data, or frontend-side authorization decision.
- No claim that Java, Redis, model provider, or Docker is live until separately
  started and verified.
- No exposure of server-only `order_item_id`, price, member identity, or raw
  trace data.

## Planned files

- `mall-ai-web/package.json`, Vite/TypeScript configuration, and entry files
- `mall-ai-web/src/api.ts` and `mall-ai-web/src/types.ts`
- `mall-ai-web/src/App.vue` and `mall-ai-web/src/style.css`
- `mall-ai-web/README.md`

## Acceptance criteria

1. A browser can submit a message and display the FastAPI response model.
2. A return proposal has a separate, explicit confirmation button; merely
   viewing it never sends a write request.
3. Product selection options are rendered from client-safe labels only.
4. The production bundle builds without TypeScript errors.
5. Live FastAPI/Java validation is documented as pending unless demonstrated.

## Build result (2026-07-31)

### Implemented

- Created `mall-ai-web`, a Vue 3 + TypeScript + Vite customer-service client.
- Added typed handling of the FastAPI customer-service response contract.
- Added client-safe rendering for verified facts, RAG sources, draft product
  options, and an explicit proposal-confirmation action.
- Added a generated browser session ID and a session-only development Token
  field. The Token is sent only as the Authorization header.

### Verified

- `npm run build`: passed; TypeScript checking and Vite production bundle
  generation completed successfully.
- `python -m unittest discover -s tests -v`: 47 tests passed in
  `mall-ai-service`.
- Vite served the new page at `http://127.0.0.1:5173`, and its `/api` proxy
  successfully forwarded the safe `GET /health` request to FastAPI.
- `npm audit --omit=dev`: no known production dependency vulnerabilities.

### Still pending

- A browser click-through of an actual customer-service message against a
  running FastAPI service and model provider.
- Java + MySQL ownership validation with a disposable real user.
- Redis-backed cross-process session persistence.
- Docker Compose and an end-to-end recorded demo.
