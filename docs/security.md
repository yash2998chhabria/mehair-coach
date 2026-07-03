# Security

Mehair Coach handles personal health data, so the default posture is private beta only.

## Data Handling

- The database starts empty.
- No personal exports or demo health records are imported.
- Each ChatGPT connector user authorizes Google separately.
- Google tokens are encrypted before storage.
- Synced health data is stored in the configured database: local SQLite for development, or hosted Turso/libSQL for the free remote deployment.

## Git Hygiene

Never commit:

- `.env`
- SQLite databases
- Turso/libSQL database tokens
- Google OAuth client secrets
- refresh tokens or access tokens
- ngrok config
- personal Fitbit exports

## OAuth

The server exposes OAuth metadata for ChatGPT, supports authorization code with PKCE, and stores separate app tokens per ChatGPT connector user. Google OAuth uses read-only Google Health scopes.

## Product Boundaries

This is coaching context, not medical advice. It should avoid diagnosis, treatment instructions, or emergency guidance.
