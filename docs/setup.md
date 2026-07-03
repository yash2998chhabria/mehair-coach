# Setup

Mehair Coach is a Python MCP server for ChatGPT Apps. ChatGPT hosts the conversation; this server handles Google Health OAuth, data sync, storage, and tools.

## Requirements

- Python 3.12 or newer.
- `uv`.
- A Google Cloud project with Google Health API enabled.
- An HTTPS tunnel or deployment URL for ChatGPT developer-mode testing.

## Environment

Generate an encryption key:

```bash
uv run python -m app.crypto
```

Create `.env` from `.env.example` and set:

- `PUBLIC_BASE_URL`: HTTPS origin ChatGPT can reach.
- `GOOGLE_REDIRECT_URI`: same origin plus `/oauth/callback/google`.
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: Google Web OAuth client credentials.
- `TOKEN_ENCRYPTION_KEY`: generated Fernet key.
- `DATABASE_URL`: default local SQLite URL is fine for private beta.

## Google Cloud

Create a Web OAuth client and add the exact `GOOGLE_REDIRECT_URI`. Keep the OAuth app in Testing mode and add every beta tester email to the OAuth test users list.

Use read-only Google Health scopes. This project intentionally excludes nutrition scopes.

## ChatGPT

Expose the server:

```bash
uv run python -m app.main
ngrok http 8787
```

Use the public URL with `/mcp` in ChatGPT developer-mode connector settings.
