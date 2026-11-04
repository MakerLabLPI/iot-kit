"""aiohttp server: the projector page, /events (SSE, a full snapshot on
every change), /api/state, and the password-protected /admin page."""
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
from pathlib import Path

from aiohttp import web

from .config import Config
from .game import Game

log = logging.getLogger("web")
STATIC = Path(__file__).parent / "static"
SSE_PING = 15  # seconds


def make_app(cfg: Config, game: Game) -> web.Application:
    app = web.Application(middlewares=[admin_auth] if cfg.admin_password else [])
    app["cfg"], app["game"] = cfg, game
    app.router.add_get("/", index)
    app.router.add_get("/events", events)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/reset", reset)
    app.router.add_get("/healthz", healthz)
    if cfg.admin_password:
        app.router.add_get("/admin", admin_page)
        app.router.add_post("/admin/api/pause", admin_pause)
        app.router.add_post("/admin/api/durations", admin_durations)
        app.router.add_post("/admin/api/kick", admin_kick)
        app.router.add_post("/admin/api/reinstate", admin_reinstate)
        app.router.add_post("/admin/api/reset", reset)
        app.router.add_get("/admin/log.csv", admin_csv)
    else:
        app.router.add_get("/admin", admin_disabled)
    app.router.add_static("/static", STATIC, append_version=True)
    return app


def page(name: str, game: Game) -> web.Response:
    """Server-rendered initial state: the snapshot is inlined into the HTML
    so the page is complete before the first SSE event arrives."""
    body = (STATIC / name).read_text(encoding="utf-8")
    # Inside <script type="application/json">: only "</" could break out,
    # and "<\/" is the same string once JSON-parsed.
    snap = json.dumps(game.snapshot()).replace("</", "<\\/")
    body = body.replace("__INITIAL_STATE__", snap)
    return web.Response(text=body, content_type="text/html",
                        headers={"Cache-Control": "no-store"})


async def index(request: web.Request) -> web.Response:
    return page("index.html", request.app["game"])


async def state(request: web.Request) -> web.Response:
    return web.json_response(request.app["game"].snapshot())


async def healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok\n")


async def reset(request: web.Request) -> web.Response:
    await request.app["game"].reset_scores()
    return web.json_response({"ok": True})


async def events(request: web.Request) -> web.StreamResponse:
    game: Game = request.app["game"]
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)
    q = game.subscribe()
    try:
        while True:
            try:
                snap = await asyncio.wait_for(q.get(), SSE_PING)
            except asyncio.TimeoutError:
                await resp.write(b": ping\n\n")
                continue
            await resp.write(b"event: state\ndata: " + json.dumps(snap).encode() + b"\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        game.unsubscribe(q)
    return resp


# --- admin -------------------------------------------------------------------

def _authorized(request: web.Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        _, _, password = base64.b64decode(auth[6:]).decode().partition(":")
    except Exception:
        return False
    return hmac.compare_digest(password, request.app["cfg"].admin_password)


@web.middleware
async def admin_auth(request: web.Request, handler):
    if request.path.startswith("/admin") and not _authorized(request):
        return web.Response(status=401, text="admin login required\n",
                            headers={"WWW-Authenticate": 'Basic realm="game-master"'})
    return await handler(request)


async def admin_disabled(request: web.Request) -> web.Response:
    return web.Response(status=404, text="admin disabled: set ADMIN_PASSWORD\n")


async def admin_page(request: web.Request) -> web.Response:
    return page("admin.html", request.app["game"])


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="JSON body expected\n")
    return data if isinstance(data, dict) else {}


async def admin_pause(request: web.Request) -> web.Response:
    data = await _body(request)
    request.app["game"].set_paused(bool(data.get("paused")))
    return web.json_response({"ok": True})


async def admin_durations(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        open_s = float(data["open"]) if data.get("open") is not None else None
        reveal_s = float(data["reveal"]) if data.get("reveal") is not None else None
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="open and reveal must be numbers\n")
    request.app["game"].set_durations(open_s, reveal_s)
    return web.json_response({"ok": True})


async def admin_kick(request: web.Request) -> web.Response:
    data = await _body(request)
    return web.json_response({"ok": request.app["game"].kick(str(data.get("id", "")))})


async def admin_reinstate(request: web.Request) -> web.Response:
    data = await _body(request)
    return web.json_response({"ok": request.app["game"].reinstate(str(data.get("id", "")))})


async def admin_csv(request: web.Request) -> web.Response:
    return web.Response(text=request.app["game"].rows_csv(), content_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="rounds.csv"'})
