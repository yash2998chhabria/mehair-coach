# Setup

mehair coach is a Python MCP server for ChatGPT Apps. ChatGPT hosts the conversation; this server handles Google Health OAuth, data sync, storage, and tools.

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
- `DATABASE_URL`: local SQLite for development, or `libsql://...` for hosted Turso/libSQL.
- `LIBSQL_AUTH_TOKEN`: required when `DATABASE_URL` points to Turso/libSQL.

For Render, `render.yaml` uses the free web tier and expects hosted persistence
through Turso/libSQL. Render also provides `RENDER_EXTERNAL_URL`, so the app can
derive its public OAuth issuer and callback URL automatically. After Render
creates the service, add this exact redirect URI to the Google Web OAuth client:

```text
https://<your-render-service>.onrender.com/oauth/callback/google
```

## Google Cloud

Create a Web OAuth client and add the exact `GOOGLE_REDIRECT_URI`. Keep the OAuth app in Testing mode and add every beta tester email to the OAuth test users list.

Use read-only Google Health scopes. This project intentionally excludes nutrition scopes.

## Free Remote Hosting

GitHub hosts the repo, but GitHub Pages cannot run this app because the MCP is a
live Python web server with OAuth callbacks. The simplest free hosted setup is
GitHub plus Render Free plus Turso Free.

The repo includes a Render Blueprint at `render.yaml`:

- Python web service on the `main` branch.
- Python 3.12.12 runtime pinned with `PYTHON_VERSION`.
- `uv sync --frozen --no-dev` build.
- `uv run --no-sync python -m app.main` start.
- `/health` health check.
- Free web instance with no persistent disk.
- Hosted SQLite-compatible persistence through Turso/libSQL.
- Secret placeholders for `DATABASE_URL`, `LIBSQL_AUTH_TOKEN`,
  `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`.

Create a Turso database, generate a database token, create the Render Blueprint
from the GitHub repo, enter the secret values in the Render dashboard, wait for
the first deploy, then add the Render callback URL to Google Cloud before
connecting the ChatGPT developer-mode connector.

## ChatGPT

Expose the server:

```bash
uv run python -m app.main
ngrok http 8787
```

Use the public URL with `/mcp` in ChatGPT developer-mode connector settings.
