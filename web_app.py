#!/usr/bin/env python3
"""Authenticated LAN control panel and canonical 240×240 preview API."""

from __future__ import annotations

import io
import secrets
from functools import wraps

from flask import Flask, jsonify, render_template, request, send_file, session

from dashboard import __version__
from dashboard.auth import AuthError, AuthStore, LoginLimiter
from dashboard.catalog import catalog_by_id, public_catalog
from dashboard.config import ConfigError, enabled_pages, load_config, normalize_config, save_config
from dashboard.display_profiles import public_profiles
from dashboard.providers import DataHub, fetch_custom_page
from dashboard.rendering import render_page
from dashboard.runtime import RuntimeStore


def create_app(test_config=None):
    test_config = test_config or {}
    state_override = test_config.get("STATE_DIR")
    auth = AuthStore(state_override)
    login_limiter = LoginLimiter()
    runtime = RuntimeStore(state_override)
    data = DataHub()

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=test_config.get("SECRET_KEY") or auth.session_secret(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=64 * 1024,
        STATE_DIR=state_override,
        TESTING=bool(test_config.get("TESTING", False)),
    )

    def is_authenticated():
        return bool(session.get("authenticated"))

    def ensure_csrf():
        token = session.get("csrf")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf"] = token
        return token

    def require_auth(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not is_authenticated():
                return jsonify({"error": "authentication_required"}), 401
            return view(*args, **kwargs)

        return wrapped

    def require_csrf(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            supplied = request.headers.get("X-CSRF-Token")
            expected = session.get("csrf")
            if not expected or not supplied or not secrets.compare_digest(supplied, expected):
                return jsonify({"error": "csrf_invalid"}), 403
            return view(*args, **kwargs)

        return wrapped

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/")
    def index():
        return render_template("index.html", version=__version__)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": __version__})

    @app.get("/api/auth/status")
    def auth_status():
        authenticated = is_authenticated()
        return jsonify(
            {
                "configured": auth.configured(),
                "authenticated": authenticated,
                "csrfToken": ensure_csrf() if authenticated else None,
            }
        )

    @app.post("/api/auth/setup")
    def auth_setup():
        payload = request.get_json(silent=True) or {}
        try:
            auth.setup(payload.get("pin"))
        except AuthError as exc:
            return jsonify({"error": str(exc)}), 400
        session.clear()
        session["authenticated"] = True
        return jsonify({"ok": True, "csrfToken": ensure_csrf()})

    @app.post("/api/auth/login")
    def auth_login():
        payload = request.get_json(silent=True) or {}
        pin = payload.get("pin")
        client = request.remote_addr or "unknown"
        if not login_limiter.allowed(client):
            return jsonify({"error": "muitas tentativas; aguarde um minuto"}), 429
        if not isinstance(pin, str) or not auth.verify(pin):
            login_limiter.record_failure(client)
            return jsonify({"error": "PIN inválido"}), 401
        login_limiter.clear(client)
        session.clear()
        session["authenticated"] = True
        return jsonify({"ok": True, "csrfToken": ensure_csrf()})

    @app.post("/api/auth/logout")
    @require_auth
    @require_csrf
    def auth_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/catalog")
    @require_auth
    def catalog():
        config = load_config(state_override)
        return jsonify({"pages": public_catalog(config["customPages"]), "displays": public_profiles()})

    @app.get("/api/config")
    @require_auth
    def get_config():
        return jsonify(load_config(state_override))

    @app.put("/api/config")
    @require_auth
    @require_csrf
    def put_config():
        payload = request.get_json(silent=True)
        try:
            normalized = save_config(payload, state_override)
        except ConfigError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(normalized)

    @app.get("/api/preview")
    @require_auth
    def preview():
        page_id = request.args.get("page", "status")
        config = load_config(state_override)
        if page_id not in catalog_by_id(config["customPages"]):
            return jsonify({"error": "página desconhecida"}), 404
        if page_id not in [page["id"] for page in enabled_pages(config)]:
            preview_config = normalize_config(config)
            for page in preview_config["pages"]:
                if page["id"] == page_id:
                    page["enabled"] = True
            config = preview_config
        page_settings = next(page for page in config["pages"] if page["id"] == page_id)
        image = render_page(page_id, data.get(config, page_id, page_settings["refreshSeconds"]), config)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", max_age=0)

    @app.post("/api/sources/test")
    @require_auth
    @require_csrf
    def test_source():
        payload = request.get_json(silent=True) or {}
        candidate = {
            "schemaVersion": 1,
            "customPages": [payload],
        }
        try:
            definition = normalize_config(candidate)["customPages"][0]
            result = fetch_custom_page(definition)
        except (ConfigError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "value": result["value"], "secondary": result["secondary"]})

    @app.get("/api/display/state")
    @require_auth
    def display_state():
        return jsonify(runtime.read_display())

    @app.post("/api/display/page")
    @require_auth
    @require_csrf
    def select_page():
        payload = request.get_json(silent=True) or {}
        page_id = payload.get("pageId")
        config = load_config(state_override)
        active_ids = [page["id"] for page in enabled_pages(config)]
        if page_id not in active_ids:
            return jsonify({"error": "página não habilitada"}), 400
        runtime.request_page(page_id)
        return jsonify({"ok": True, "pageId": page_id})

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify({"error": "payload_too_large"}), 413

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8080, debug=False)
