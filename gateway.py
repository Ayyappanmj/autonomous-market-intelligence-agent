"""Single-port gateway for one-service deployments (e.g. Render free tier).

* The public REST API (/health, /docs, /openapi.json, /api/v1/...) is served in-process by FastAPI.
* Every other path is reverse-proxied (HTTP and WebSocket) to the Streamlit dashboard bound to loopback.

The upstream host is fixed; request paths can never redirect the proxy elsewhere.
Run:  uvicorn gateway:create_gateway_app --factory --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Optional

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from websockets.asyncio.client import connect as default_ws_connect

from app.main import create_app
from app.gateway_utils import filter_headers, upstream_url
from app.utils.logging import get_logger

log = get_logger(__name__)
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
MAX_WS_MESSAGE = 8 * 1024 * 1024


def create_gateway_app(settings=None, repo=None, fetcher=None, llm=None, upstream: Optional[str] = None,
                       http_client: Optional[httpx.AsyncClient] = None,
                       ws_connect: Optional[Callable[..., Any]] = None) -> FastAPI:
    upstream = (upstream or os.getenv("DASHBOARD_UPSTREAM", "http://127.0.0.1:8501")).rstrip("/")
    ws_base = "ws" + upstream[len("http"):]
    client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    connector = ws_connect or default_ws_connect

    app = create_app(settings, repo, fetcher, llm)
    # In gateway mode "/" belongs to the dashboard, so drop the API's info route.
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/"]

    @app.on_event("shutdown")
    async def _close_client() -> None:
        await client.aclose()

    @app.api_route("/{path:path}", methods=METHODS, include_in_schema=False)
    async def dashboard_http(path: str, request: Request):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        url = upstream_url(upstream, path, request.url.query)
        headers = filter_headers(request.headers.items(), drop=("host", "content-length"))
        headers.append(("host", request.headers.get("host", "")))
        try:
            body = await request.body()
            upstream_req = client.build_request(request.method, url, headers=headers, content=body)
            resp = await client.send(upstream_req, stream=True)
        except httpx.HTTPError:
            return JSONResponse({"detail": "Dashboard is starting or unavailable. Please retry shortly."},
                                status_code=502)
        async def body_stream():
            if hasattr(resp, "_content"):
                yield resp.content
            else:
                async for chunk in resp.aiter_raw():
                    yield chunk

        out = StreamingResponse(body_stream(), status_code=resp.status_code,
                                background=BackgroundTask(resp.aclose))
        for k, v in filter_headers(resp.headers.multi_items()):
            out.headers.append(k, v)
        return out

    @app.websocket("/{path:path}")
    async def dashboard_ws(websocket: WebSocket, path: str):
        target = upstream_url(ws_base, path, websocket.url.query)
        protocols = websocket.scope.get("subprotocols") or None
        cm = connector(target, subprotocols=protocols, max_size=MAX_WS_MESSAGE, open_timeout=10)
        try:
            upstream_ws = await cm.__aenter__()
        except Exception as exc:  # upstream down/refused: close cleanly, never leak details
            log.warning("ws upstream unavailable", extra={"error_type": type(exc).__name__})
            await websocket.close(code=1011)
            return
        try:
            await websocket.accept(subprotocol=getattr(upstream_ws, "subprotocol", None))

            async def client_to_upstream() -> None:
                while True:
                    msg = await websocket.receive()
                    if msg["type"] == "websocket.disconnect":
                        return
                    if msg.get("text") is not None:
                        await upstream_ws.send(msg["text"])
                    elif msg.get("bytes") is not None:
                        await upstream_ws.send(msg["bytes"])

            async def upstream_to_client() -> None:
                async for message in upstream_ws:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                try:
                    t.exception()  # mark retrieved; connection errors simply end the session
                except asyncio.CancelledError:
                    pass
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            await cm.__aexit__(None, None, None)

    return app
