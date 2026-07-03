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

It also includes golden coaching evals in `tests/test_coach_evals.py`. These
seed realistic local Fitbit-like records and validate that the assistant stack
uses the right signals for real questions:

- under-recovered/tired day: short sleep, suppressed HRV, elevated resting HR,
  high recent zone minutes, low energy, and soreness should produce an easy day
  with specific evidence.
- green training day: strong sleep, HRV above baseline, stable resting HR, low
  soreness, and goal context should keep harder training available.
- stale data: time-sensitive workout questions should ask for sync before
  confident advice.
- heart-safety question: high resting HR plus dizziness/concern language should
  produce medical caution instead of pure training advice.

Run a local server:

```bash
uv run python -m app.main
```

Health check:

```bash
curl http://localhost:8787/health
```

Widget preview:

```bash
open "http://localhost:8787/docs/widget-preview?state=health-clues"
```

Available preview states are `health-clues`, `today-workout`,
`recovery-comparison`, and `heart-safety`. These render the same Apps SDK
iframe HTML with synthetic structured tool results, which makes visual QA
possible without recreating a ChatGPT connector for every UI change.

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
- `I feel cooked today. Which metrics matter, and what clues do you see?`
- `Should I worry about my high heart rate and dizziness?`
