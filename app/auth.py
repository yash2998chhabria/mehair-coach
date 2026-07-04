from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .crypto import TokenCipher
from .db import Database, dumps, loads
from .settings import Settings
from .time_utils import iso_now, utc_timestamp
from .tokens import new_token, token_hash


class AuthError(Exception):
    pass


class AppTokenVerifier(TokenVerifier):
    def __init__(self, service: AuthService):
        self.service = service

    async def verify_token(self, token: str) -> AccessToken | None:
        row = self.service.load_access_token(token)
        if not row:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=row["scopes"].split(),
            expires_at=row["expires_at"],
            subject=row["user_id"],
        )


class AuthService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def oauth_metadata(self) -> dict[str, Any]:
        base = self.settings.base_url
        return {
            "issuer": base,
            "client_name": "Mehair Coach",
            "logo_uri": f"{base}/assets/mehair-coach-icon.svg",
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_post",
                "client_secret_basic",
            ],
            "scopes_supported": [self.settings.app_scope],
            "service_documentation": f"{base}/docs/setup",
        }

    async def register_client(self, request: Request) -> JSONResponse:
        body = await request.json()
        if not body.get("redirect_uris"):
            return JSONResponse(
                {
                    "error": "invalid_client_metadata",
                    "error_description": "redirect_uris is required.",
                },
                status_code=400,
            )
        client_id = body.get("client_id") or secrets.token_urlsafe(18)
        auth_method = body.get("token_endpoint_auth_method") or "none"
        client_secret = (
            secrets.token_urlsafe(32) if auth_method != "none" else None
        )
        now = iso_now()
        metadata = {
            **body,
            "client_id": client_id,
            "client_id_issued_at": utc_timestamp(),
            "token_endpoint_auth_method": auth_method,
            "grant_types": body.get("grant_types") or ["authorization_code", "refresh_token"],
            "response_types": body.get("response_types") or ["code"],
        }
        if client_secret:
            metadata["client_secret"] = client_secret
            metadata["client_secret_expires_at"] = 0
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_clients
                  (client_id, client_secret, metadata_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (client_id, client_secret, dumps(metadata), now),
            )
        return JSONResponse(metadata, status_code=201)

    async def authorize(self, request: Request) -> Response:
        params = dict(request.query_params)
        required = ["client_id", "redirect_uri", "response_type", "code_challenge"]
        missing = [name for name in required if not params.get(name)]
        if missing:
            return JSONResponse(
                {"error": "invalid_request", "error_description": f"Missing: {', '.join(missing)}"},
                status_code=400,
            )
        if params.get("response_type") != "code":
            return JSONResponse(
                {"error": "unsupported_response_type"},
                status_code=400,
            )
        if params.get("code_challenge_method", "S256") != "S256":
            return JSONResponse(
                {
                    "error": "invalid_request",
                    "error_description": "Only S256 PKCE is supported.",
                },
                status_code=400,
            )
        try:
            self._ensure_client(params["client_id"], params["redirect_uri"])
        except AuthError as exc:
            return JSONResponse(
                {"error": "invalid_request", "error_description": str(exc)},
                status_code=400,
            )

        if not (
            self.settings.google_client_id
            and self.settings.google_client_secret
            and self.settings.token_encryption_key
        ):
            return HTMLResponse(
                """
                <h1>Mehair Coach setup needed</h1>
                <p>Google OAuth and TOKEN_ENCRYPTION_KEY must be configured before connecting.</p>
                """,
                status_code=503,
            )

        google_state = secrets.token_urlsafe(32)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO oauth_states (state, payload_json, created_at) VALUES (?, ?, ?)",
                (google_state, dumps(params), utc_timestamp()),
            )

        google_params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_callback_url,
            "response_type": "code",
            "scope": " ".join(self.settings.google_scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": google_state,
        }
        return RedirectResponse(
            "https://accounts.google.com/o/oauth2/v2/auth?"
            + urlencode(google_params)
        )

    async def google_callback(
        self,
        request: Request,
        on_connected: Callable[[str], None] | None = None,
    ) -> Response:
        error = request.query_params.get("error")
        if error:
            return HTMLResponse(f"<h1>Google OAuth failed</h1><p>{error}</p>", status_code=400)
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return HTMLResponse("<h1>Missing Google OAuth code/state.</h1>", status_code=400)

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        if not row:
            return HTMLResponse("<h1>Expired OAuth state. Please try again.</h1>", status_code=400)

        original = loads(row["payload_json"], {})
        google_tokens = await self._exchange_google_code(code)
        user_info = await self._load_google_user_info(google_tokens["access_token"])
        user_id = self._create_user_from_google(google_tokens, user_info)
        if on_connected:
            on_connected(user_id)
        app_code = self._create_authorization_code(user_id, original)

        redirect_uri = original["redirect_uri"]
        redirect_params = {"code": app_code}
        if original.get("state"):
            redirect_params["state"] = original["state"]
        return RedirectResponse(f"{redirect_uri}?{urlencode(redirect_params)}")

    async def token(self, request: Request) -> JSONResponse:
        form = await request.form()
        grant_type = str(form.get("grant_type", ""))
        client = self._authenticate_client(request, form)
        if grant_type == "authorization_code":
            return self._exchange_app_code(client, form)
        if grant_type == "refresh_token":
            return self._exchange_refresh_token(client, form)
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    def load_access_token(self, token: str) -> dict[str, Any] | None:
        now = utc_timestamp()
        row = self.db.one(
            """
            SELECT token_hash, user_id, client_id, scopes, expires_at
            FROM app_access_tokens
            WHERE token_hash = ? AND expires_at > ?
            """,
            (token_hash(token), now),
        )
        return dict(row) if row else None

    def current_user_google_token(self, user_id: str) -> str | None:
        row = self.db.one(
            "SELECT access_token_encrypted FROM google_tokens WHERE user_id = ?",
            (user_id,),
        )
        if not row or not row["access_token_encrypted"]:
            return None
        return self._cipher().decrypt(row["access_token_encrypted"])

    def refresh_token_available(self, user_id: str) -> bool:
        row = self.db.one(
            "SELECT refresh_token_encrypted FROM google_tokens WHERE user_id = ?",
            (user_id,),
        )
        return bool(row and row["refresh_token_encrypted"])

    async def ensure_google_access_token(self, user_id: str) -> str | None:
        row = self.db.one(
            """
            SELECT refresh_token_encrypted, access_token_encrypted, access_token_expires_at
            FROM google_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if not row:
            return None
        cipher = self._cipher()
        if row["access_token_encrypted"] and (row["access_token_expires_at"] or 0) > utc_timestamp() + 60:
            return cipher.decrypt(row["access_token_encrypted"])
        if not row["refresh_token_encrypted"]:
            return None
        refresh_token = cipher.decrypt(row["refresh_token_encrypted"])
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        response.raise_for_status()
        payload = response.json()
        access_token = payload["access_token"]
        expires_at = utc_timestamp() + int(payload.get("expires_in", 3600))
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE google_tokens
                SET access_token_encrypted = ?, access_token_expires_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (cipher.encrypt(access_token), expires_at, iso_now(), user_id),
            )
        return access_token

    def _ensure_client(self, client_id: str, redirect_uri: str) -> None:
        existing = self.db.one(
            "SELECT metadata_json FROM oauth_clients WHERE client_id = ?",
            (client_id,),
        )
        if existing:
            metadata = loads(existing["metadata_json"], {})
            registered_redirects = metadata.get("redirect_uris") or []
            if registered_redirects and redirect_uri not in registered_redirects:
                raise AuthError("redirect_uri is not registered for this client")
            return
        metadata = {
            "client_id": client_id,
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_clients (client_id, client_secret, metadata_json, created_at)
                VALUES (?, NULL, ?, ?)
                """,
                (client_id, dumps(metadata), iso_now()),
            )

    def _authenticate_client(self, request: Request, form: Any) -> dict[str, Any]:
        client_id = str(form.get("client_id") or "")
        if not client_id:
            raise AuthError("Missing client_id")
        row = self.db.one(
            "SELECT client_id, client_secret, metadata_json FROM oauth_clients WHERE client_id = ?",
            (client_id,),
        )
        if not row:
            raise AuthError("Invalid client_id")
        metadata = loads(row["metadata_json"], {})
        method = metadata.get("token_endpoint_auth_method") or "none"
        if method == "none":
            return dict(row)
        provided_secret = str(form.get("client_secret") or "")
        if method == "client_secret_basic":
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                decoded = base64.b64decode(auth_header.removeprefix("Basic ")).decode()
                _, provided_secret = decoded.split(":", 1)
        if not row["client_secret"] or not secrets.compare_digest(
            row["client_secret"], provided_secret
        ):
            raise AuthError("Invalid client secret")
        return dict(row)

    def _exchange_app_code(self, client: dict[str, Any], form: Any) -> JSONResponse:
        code = str(form.get("code") or "")
        verifier = str(form.get("code_verifier") or "")
        row = self.db.one(
            """
            SELECT * FROM oauth_codes
            WHERE code = ? AND client_id = ? AND used = 0 AND expires_at > ?
            """,
            (code, client["client_id"], utc_timestamp()),
        )
        if not row:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if not self._verify_pkce(verifier, row["code_challenge"]):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        redirect_uri = str(form.get("redirect_uri") or "")
        if redirect_uri and redirect_uri != row["redirect_uri"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        resource = str(form.get("resource") or "")
        if resource and row["resource"] and resource != row["resource"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        with self.db.connect() as conn:
            conn.execute("UPDATE oauth_codes SET used = 1 WHERE code = ?", (code,))
        return self._issue_app_tokens(row["user_id"], client["client_id"], row["scopes"].split())

    def _exchange_refresh_token(self, client: dict[str, Any], form: Any) -> JSONResponse:
        refresh_token = str(form.get("refresh_token") or "")
        row = self.db.one(
            """
            SELECT * FROM app_refresh_tokens
            WHERE token_hash = ? AND client_id = ? AND expires_at > ?
            """,
            (token_hash(refresh_token), client["client_id"], utc_timestamp()),
        )
        if not row:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return self._issue_app_tokens(row["user_id"], client["client_id"], row["scopes"].split())

    def _issue_app_tokens(self, user_id: str, client_id: str, scopes: list[str]) -> JSONResponse:
        access_token = new_token("mhc_at")
        refresh_token = new_token("mhc_rt")
        now = utc_timestamp()
        access_expires_at = now + self.settings.access_token_ttl_seconds
        refresh_expires_at = now + self.settings.refresh_token_ttl_seconds
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_access_tokens
                  (token_hash, user_id, client_id, scopes, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash(access_token),
                    user_id,
                    client_id,
                    " ".join(scopes),
                    access_expires_at,
                    iso_now(),
                ),
            )
            conn.execute(
                """
                INSERT INTO app_refresh_tokens
                  (token_hash, user_id, client_id, scopes, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash(refresh_token),
                    user_id,
                    client_id,
                    " ".join(scopes),
                    refresh_expires_at,
                    iso_now(),
                ),
            )
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": self.settings.access_token_ttl_seconds,
                "refresh_token": refresh_token,
                "scope": " ".join(scopes),
            }
        )

    def _create_authorization_code(self, user_id: str, original: dict[str, Any]) -> str:
        code = new_token("mhc_code")
        scopes = (original.get("scope") or self.settings.app_scope).split()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_codes
                  (code, user_id, client_id, redirect_uri, code_challenge, scopes,
                   resource, expires_at, used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    code,
                    user_id,
                    original["client_id"],
                    original["redirect_uri"],
                    original["code_challenge"],
                    " ".join(scopes),
                    original.get("resource"),
                    utc_timestamp() + 300,
                ),
            )
        return code

    def _create_user_from_google(self, google_tokens: dict[str, Any], user_info: dict[str, Any]) -> str:
        cipher = self._cipher()
        now = iso_now()
        expires_at = utc_timestamp() + int(google_tokens.get("expires_in", 3600))
        existing = None
        if user_info.get("sub"):
            existing = self.db.one(
                "SELECT id FROM users WHERE google_subject = ?",
                (user_info["sub"],),
            )
        user_id = existing["id"] if existing else f"user_{secrets.token_urlsafe(18)}"
        refresh_token = google_tokens.get("refresh_token")
        refresh_token_encrypted = cipher.encrypt(refresh_token) if refresh_token else None
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, google_email, google_subject, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  google_email = excluded.google_email,
                  google_subject = excluded.google_subject,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    user_info.get("email"),
                    user_info.get("sub"),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO google_tokens
                  (user_id, refresh_token_encrypted, access_token_encrypted,
                   access_token_expires_at, scopes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  refresh_token_encrypted = COALESCE(excluded.refresh_token_encrypted, google_tokens.refresh_token_encrypted),
                  access_token_encrypted = excluded.access_token_encrypted,
                  access_token_expires_at = excluded.access_token_expires_at,
                  scopes = excluded.scopes,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    refresh_token_encrypted,
                    cipher.encrypt(google_tokens["access_token"]),
                    expires_at,
                    google_tokens.get("scope", " ".join(self.settings.google_scopes)),
                    now,
                ),
            )
        return user_id

    async def _exchange_google_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.google_callback_url,
                    "grant_type": "authorization_code",
                },
            )
        response.raise_for_status()
        return response.json()

    async def _load_google_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 400:
            return {}
        return response.json()

    def _cipher(self) -> TokenCipher:
        return TokenCipher(self.settings.token_encryption_key)

    @staticmethod
    def _verify_pkce(verifier: str, challenge: str) -> bool:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return secrets.compare_digest(computed, challenge)
