from __future__ import annotations

import base64
import hashlib

from app.auth import AuthService
from app.crypto import generate_key
from app.db import Database
from app.settings import Settings


def make_auth(tmp_path) -> AuthService:
    settings = Settings(
        public_base_url="http://localhost:8787",
        database_url=f"sqlite:///{tmp_path / 'auth.sqlite3'}",
        token_encryption_key=generate_key(),
        google_client_id="google-client",
        google_client_secret="google-secret",
    )
    db = Database(settings.sqlite_path)
    db.init()
    return AuthService(db, settings)


def test_oauth_metadata_advertises_pkce_and_dcr(tmp_path) -> None:
    auth = make_auth(tmp_path)

    metadata = auth.oauth_metadata()

    assert metadata["issuer"] == "http://localhost:8787"
    assert metadata["authorization_endpoint"].endswith("/oauth/authorize")
    assert metadata["token_endpoint"].endswith("/oauth/token")
    assert metadata["registration_endpoint"].endswith("/oauth/register")
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert "none" in metadata["token_endpoint_auth_methods_supported"]
    assert metadata["scopes_supported"] == ["health.read"]


def test_pkce_verifier_validation(tmp_path) -> None:
    auth = make_auth(tmp_path)
    verifier = "correct-horse-battery-staple"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    assert auth._verify_pkce(verifier, challenge)
    assert not auth._verify_pkce("wrong", challenge)


def test_google_tokens_are_encrypted_and_refresh_token_is_preserved(tmp_path) -> None:
    auth = make_auth(tmp_path)

    user_id = auth._create_user_from_google(
        {
            "access_token": "sample_access_one",
            "refresh_token": "sample_refresh_one",
            "expires_in": 3600,
            "scope": "scope-a",
        },
        {"email": "tester@example.com", "sub": "google-subject"},
    )
    same_user_id = auth._create_user_from_google(
        {
            "access_token": "sample_access_two",
            "expires_in": 3600,
            "scope": "scope-a",
        },
        {"email": "tester@example.com", "sub": "google-subject"},
    )

    assert same_user_id == user_id
    assert auth.refresh_token_available(user_id)
    assert auth.current_user_google_token(user_id) == "sample_access_two"

    row = auth.db.one(
        "SELECT access_token_encrypted, refresh_token_encrypted FROM google_tokens WHERE user_id = ?",
        (user_id,),
    )
    assert row is not None
    assert "sample_access_two" not in row["access_token_encrypted"]
    assert "sample_refresh_one" not in row["refresh_token_encrypted"]
