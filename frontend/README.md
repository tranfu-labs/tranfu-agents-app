# TRANFU//AGENTS Dashboard Frontend

React + TypeScript dashboard for the FastAPI collector.

## Commands

```bash
npm ci
npm run dev
npm run build
```

The Vite dev server proxies API and shim requests to `http://localhost:8788`.
Production builds are copied into the Python runtime image by the root
`Dockerfile`; do not commit `dist/`.
