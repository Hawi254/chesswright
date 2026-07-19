// The built app (frontend/dist) is served by api/main.py itself, same
// origin as the API -- so relative paths always reach the right port,
// including the random one desktop_app.free_port() assigns per launch
// (found live 2026-07-13: every hook had this hardcoded to the fixed
// port used for manual `npm run dev` testing, which is never the port
// the packaged app actually starts on, so every fetch failed silently
// with "Couldn't load your Overview data."). Only `npm run dev` (Vite on
// 5173) needs an absolute URL, since it's a different origin than the
// separately-run `uvicorn api.main:app --port 8123` dev server.
export const API_BASE = import.meta.env.DEV ? 'http://127.0.0.1:8123' : ''
