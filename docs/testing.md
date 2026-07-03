# Testing

Run unit tests:

```bash
uv run pytest
```

The suite includes a local private-beta E2E flow that simulates ChatGPT and
Google without creating live credentials. It drives OAuth client registration,
authorize/callback/token exchange, bearer-authenticated MCP JSON-RPC calls,
Google Health sync, empty states, coaching outputs, refresh token exchange,
unauthenticated challenges, and sync failure handling.

Run a local server:

```bash
uv run python -m app.main
```

Health check:

```bash
curl http://localhost:8787/health
```

MCP Inspector:

```bash
npx @modelcontextprotocol/inspector@latest --server-url http://localhost:8787/mcp --transport http
```

For ChatGPT end-to-end testing, expose the server with HTTPS, create a developer-mode connector, then complete Google OAuth only for the account being tested.

Golden prompts:

- `Sync latest Fitbit data.`
- `How hard should I work out today?`
- `Why?`
- `Compare my sleep and heart rate.`
- `Show my activity load this week.`
