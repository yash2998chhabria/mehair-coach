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
  with specific evidence, goal progress, and check-in context.
- all-data overview: the returned daily brief should include training bias,
  priority signals, a short plan, confidence, and useful follow-up prompts.
- daily-plan questions: vague prompts like `What should I do today?` should
  route through the daily brief plus workout recommendation tools.
- context gaps: if goals or subjective check-ins are missing, overview and
  workout tools should surface that before hard-training advice.
- active workout guidance: live HR/RPE/pain/symptom prompts should return
  continue, downshift, stop, or safety-check guidance without diagnosing.
- green training day: strong sleep, HRV above baseline, stable resting HR, low
  soreness, strong energy, and goal context should keep harder training
  available.
- workout recommendations: the returned `evidence`/`why` trail should name the
  readiness signals, data freshness, latest load, check-ins, goal progress, and
  recent workout history used for the decision.
- stale data: time-sensitive workout questions should ask for sync before
  confident advice.
- heart-safety question: high resting HR plus dizziness/concern language should
  produce medical caution instead of pure training advice.
- large synced dataset: high-frequency heart samples plus 30 days of daily
  records should keep question clues fast, compact, and free of raw payload
  dumps.

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

Available preview states are `health-overview`, `health-clues`, `today-workout`,
`active-workout`, `recovery-comparison`, and `heart-safety`. These render the same Apps SDK
iframe HTML with synthetic structured tool results, which makes visual QA
possible without recreating a ChatGPT connector for every UI change.

MCP Inspector:

```bash
npx @modelcontextprotocol/inspector@latest --server-url http://localhost:8787/mcp --transport http
```

For ChatGPT end-to-end testing, expose the server with HTTPS, create a developer-mode connector, then complete Google OAuth only for the account being tested.

Golden prompts:

- `Sync latest Fitbit data and give me a full health and fitness overview using all my data.`
- `What should I do today?`
- `How hard should I work out today?`
- `I am 18 minutes into intervals, heart rate 178, RPE 9, and I feel dizzy. Should I keep going?`
- `Why?`
- `Compare my sleep and heart rate.`
- `Show my activity load this week.`
- `I feel cooked today. Which metrics matter, and what clues do you see?`
- `Should I worry about my high heart rate and dizziness?`

If ChatGPT answers that it cannot access the connector while the connector is enabled, immediately retry with `Use the Mehair Coach Live connector tools now. Call sync_and_get_health_overview.` This catches developer-mode routing/cache misses during live testing.
