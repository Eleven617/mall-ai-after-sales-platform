# mall-ai-web

Focused Vue 3 demonstration client for `mall-ai-service`.

## What it demonstrates

- A stable browser `session_id` for multi-turn customer-service continuation.
- Real mall username/password login through FastAPI and Java; the Java-issued
  Bearer Token is stored in browser `sessionStorage` and forwarded by the client.
- Server-rendered answers, verified business fact cards, return-draft product
  selection, and explicit return-proposal confirmation. RAG source metadata is
  kept on the service side and is not shown to customers.

The browser never receives or supplies an internal `order_item_id`, price,
member identity, authorization decision, or raw trace data.

## Local development

1. Start FastAPI and the Java mall service.
2. Install packages once: `npm install`.
3. Start the UI: `npm run dev`.
4. Open the Vite URL, normally `http://127.0.0.1:5173`.

During development, Vite proxies `/api/*` to FastAPI. Override the target when
needed:

```powershell
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8000"
npm run dev
```

For a local Java-protected order query, log in with a disposable local mall
account through the UI. The browser never asks a customer to paste a raw Token
into the chat or settings panel.

## Honest verification status

- The client is designed against the existing FastAPI response schema.
- `npm run build` verifies TypeScript and the production bundle.
- Root Docker Compose packages the Vue build behind Nginx and proxies `/api/*`
  to FastAPI. Container runtime verification remains separate until Docker
  Desktop has built and started the full local stack.
