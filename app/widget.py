from __future__ import annotations

import json


WIDGET_URI = "ui://mehair/today-v4.html"
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"


TODAY_WIDGET_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mehair Coach</title>
    <style>
      :root {
        color-scheme: light;
        --ink: #171a1f;
        --muted: #667078;
        --line: #dde3df;
        --surface: #ffffff;
        --wash: #f5f7f4;
        --tile: #fafbf9;
        --accent: #39745c;
        --accent-soft: #edf5f0;
        --warn: #9b741c;
        --danger: #a94f43;
        --info: #386f8f;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
      }

      * { box-sizing: border-box; }

      html,
      body {
        margin: 0;
        min-height: 100%;
      }

      body {
        background: var(--wash);
        color: var(--ink);
        padding: 10px;
      }

      main {
        margin: 0 auto;
        max-width: 660px;
      }

      .panel {
        --accent: #39745c;
        --accent-soft: #edf5f0;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 1px 2px rgba(17, 24, 39, 0.05);
        overflow: hidden;
      }

      .empty {
        display: grid;
        gap: 8px;
        padding: 18px;
        color: #404a52;
        font-size: 14px;
        line-height: 1.4;
      }

      .empty strong {
        color: var(--ink);
        font-size: 15px;
      }

      .mast {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 14px;
        align-items: start;
        padding: 14px 14px 8px;
        border-bottom: 1px solid #edf0ea;
      }

      .identity {
        min-width: 0;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: var(--accent);
        font-size: 11px;
        font-weight: 820;
        letter-spacing: 0;
        text-transform: uppercase;
      }

      h1 {
        margin: 0;
        color: var(--ink);
        font-size: 18px;
        font-weight: 820;
        line-height: 1.16;
      }

      .headline {
        margin: 7px 0 0;
        color: #333d45;
        font-size: 13px;
        line-height: 1.38;
      }

      .stamp {
        min-width: 96px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.3;
        text-align: right;
      }

      .status-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        padding: 0 14px 12px;
      }

      .chip {
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        border: 1px solid #d9e1dc;
        border-radius: 999px;
        background: #fff;
        color: #313940;
        font-size: 12px;
        font-weight: 720;
        line-height: 1;
        padding: 5px 9px;
        text-transform: capitalize;
      }

      .chip.accent {
        border-color: var(--accent);
        background: var(--accent-soft);
        color: #173d31;
      }

      .hero {
        display: grid;
        grid-template-columns: 136px 1fr;
        gap: 12px;
        padding: 14px;
      }

      .gauge {
        position: relative;
        display: grid;
        place-items: center;
        width: 136px;
        aspect-ratio: 1;
        min-height: 136px;
        border: 1px solid #dfe6e1;
        border-radius: 50%;
        background: conic-gradient(var(--accent) calc(var(--score, 0) * 1%), #e8ece8 0);
        overflow: hidden;
      }

      .gauge-inner {
        display: grid;
        gap: 2px;
        place-items: center;
        width: 92px;
        height: 92px;
        border: 1px solid #e5eae6;
        border-radius: 50%;
        background: #fff;
      }

      .gauge b {
        color: var(--ink);
        font-size: 30px;
        font-weight: 840;
        line-height: 1.1;
      }

      .gauge span {
        color: var(--muted);
        font-size: 11px;
        font-weight: 720;
        line-height: 1.2;
        text-align: center;
      }

      .plan-box {
        display: grid;
        gap: 10px;
        align-content: start;
        min-width: 0;
        border: 1px solid #dfe6e1;
        border-radius: 8px;
        background: #fbfcfb;
        padding: 12px;
      }

      .plan-box h2 {
        margin: 0;
        color: var(--ink);
        font-size: 14px;
        font-weight: 780;
        line-height: 1.2;
      }

      .plan-box p {
        margin: 0;
        color: #3b454d;
        font-size: 13px;
        line-height: 1.38;
      }

      .focus-list {
        display: grid;
        gap: 6px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .focus-list li {
        border-left: 3px solid var(--accent);
        padding-left: 8px;
        color: #303942;
        font-size: 12px;
        line-height: 1.34;
      }

      .metrics {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }

      .metric {
        display: grid;
        align-content: center;
        min-height: 76px;
        border: 1px solid #e4e9e4;
        border-radius: 8px;
        background: var(--tile);
        padding: 10px;
      }

      .metric b {
        display: block;
        overflow-wrap: anywhere;
        color: #20272e;
        font-size: 18px;
        font-weight: 800;
        line-height: 1.1;
      }

      .metric span {
        display: block;
        margin-top: 5px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.25;
      }

      .metric small {
        display: block;
        margin-top: 4px;
        color: #89939a;
        font-size: 11px;
        line-height: 1.25;
      }

      .details {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        border-top: 1px solid #edf0ea;
        background: #fcfdfb;
        padding: 12px 14px 14px;
      }

      .section {
        min-width: 0;
      }

      .section h3 {
        margin: 0 0 8px;
        color: #59636b;
        font-size: 12px;
        font-weight: 800;
        line-height: 1.2;
      }

      .evidence {
        display: grid;
        gap: 7px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .evidence li {
        color: #343d45;
        font-size: 12px;
        line-height: 1.35;
      }

      .evidence li::before {
        content: "";
        display: inline-block;
        width: 6px;
        height: 6px;
        margin-right: 7px;
        border-radius: 999px;
        background: var(--accent);
        vertical-align: 1px;
      }

      @media (max-width: 560px) {
        body { padding: 8px; }
        .mast { grid-template-columns: 1fr; gap: 8px; }
        .stamp { min-width: 0; text-align: left; }
        .hero { grid-template-columns: 1fr; }
        .gauge { justify-self: center; min-height: 136px; }
        .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .details { grid-template-columns: 1fr; }
      }

      @media (max-width: 340px) {
        .metrics { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="panel" id="root">
        <div class="empty">
          <strong>Mehair Coach</strong>
          <span>Waiting for health context.</span>
        </div>
      </section>
    </main>
    <script>
      const root = document.getElementById("root");

      const state = { data: null };
      const pending = new Map();
      let nextId = 1;

      function rpcRequest(method, params) {
        const id = nextId++;
        const message = { jsonrpc: "2.0", id, method, params };
        window.parent.postMessage(message, "*");
        return new Promise((resolve, reject) => {
          pending.set(id, { resolve, reject });
          setTimeout(() => {
            if (pending.has(id)) {
              pending.delete(id);
              reject(new Error("Timed out waiting for host."));
            }
          }, 8000);
        });
      }

      function rpcNotify(method, params) {
        window.parent.postMessage({ jsonrpc: "2.0", method, params }, "*");
      }

      function updateFromResponse(response) {
        const data = response?.structuredContent || response?.result?.structuredContent || response;
        if (data && typeof data === "object") {
          state.data = data;
          render();
        }
      }

      window.addEventListener("message", (event) => {
        const message = event.data || {};
        if (message.id && pending.has(message.id)) {
          const waiter = pending.get(message.id);
          pending.delete(message.id);
          if (message.error) waiter.reject(message.error);
          else waiter.resolve(message.result);
          return;
        }
        if (message.method === "ui/notifications/tool-result") {
          updateFromResponse(message.params);
        }
      }, { passive: true });

      async function initialize() {
        try {
          await rpcRequest("ui/initialize", {
            appInfo: { name: "mehair-coach-widget", version: "0.3.0" },
            appCapabilities: {},
            protocolVersion: "2026-01-26",
          });
          rpcNotify("ui/notifications/initialized", {});
        } catch (error) {
          console.error(error);
        }
      }

      function render() {
        const data = state.data || {};
        const status = data.status;
        if (status && status !== "ok" && status !== "connected") {
          renderEmpty(data.message || "No synced Fitbit data yet.", data.status || "setup");
          return;
        }
        renderModel(toViewModel(data));
      }

      function renderEmpty(message, status) {
        root.style.setProperty("--accent", "#667078");
        root.style.setProperty("--accent-soft", "#f1f3f4");
        root.innerHTML = `
          <div class="empty">
            <strong>${escapeHtml(status === "empty" ? "No synced data yet" : "Setup needed")}</strong>
            <span>${escapeHtml(message)}</span>
          </div>
        `;
      }

      function toViewModel(data) {
        if (data?.overview_type === "health_overview" && data?.sections) return healthOverviewModel(data);
        if (data?.clue_type === "health_question_clues") return questionCluesModel(data);
        if (data?.comparison_type === "sleep_heart_recovery") return recoveryComparisonModel(data);
        if (data?.planned_activity && Array.isArray(data.session_guidance)) return workoutPlanModel(data);
        if (data?.recommendation && Array.isArray(data.next_actions) && data?.goal_context) return todayWorkoutModel(data);
        if (data?.latest && Array.isArray(data.days) && (data.latest.stages_minutes || data.latest.sessions_count != null)) {
          return sleepModel(data);
        }
        if (data?.totals && data?.highest_load_day && Array.isArray(data.days)) return activityModel(data);
        if (data?.summary && Array.isArray(data.days) && ("average_hrv_ms" in data.summary || "average_resting_bpm" in data.summary)) {
          return heartModel(data);
        }
        if (data?.metrics && data?.requested_metrics) return metricQueryModel(data);
        return readinessModel(data);
      }

      function healthOverviewModel(data) {
        const readiness = data.readiness || {};
        const label = readiness.label || "pending";
        const sections = data.sections || {};
        const activity = sections.activity || {};
        const sleep = sections.sleep || {};
        const heart = sections.heart || {};
        const recovery = sections.recovery || {};
        const workouts = sections.workouts || {};
        const dataUsed = data.data_used || {};
        const freshness = data.data_freshness || {};
        const dateRange = data.date_range || {};
        const range = dateRange.start && dateRange.end ? `${dateRange.start} to ${dateRange.end}` : "";
        const sleepHours = sleep.latest_asleep_hours ?? data.today?.sleep?.asleep_hours ?? data.today?.sleep?.duration_hours;
        const hrv = heart.latest_hrv_ms ?? data.today?.hrv_ms;
        const rhr = heart.latest_resting_heart_rate ?? data.today?.resting_heart_rate;
        const primaryActions = (data.next_actions || []).slice(0, 4);
        return {
          accent: readinessAccent(label),
          title: "Health Overview",
          eyebrow: "Mehair Coach",
          date: range || data.data_freshness?.latest_observed_date || "",
          chips: [
            label,
            `${data.window_days || 14} days`,
            `${dataUsed.synced_metric_count || 0} metrics`,
            freshnessChip(freshness),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: data.headline || readiness.recommendation || "All synced health data summarized.",
          focusTitle: "Next Actions",
          focus: primaryActions,
          metrics: [
            ["Steps", intText(activity.totals?.steps ?? data.today?.steps ?? 0), "window"],
            ["Zone min", intText(activity.totals?.active_zone_minutes ?? data.today?.active_zone_minutes ?? 0), "window"],
            ["Sleep", sleepHours ? `${num(sleepHours, 1)}h` : null, sleep.days_with_sleep ? `${sleep.days_with_sleep} nights` : ""],
            ["HRV", hrv ? `${num(hrv, 1)} ms` : null, heart.average_hrv_ms ? `avg ${num(heart.average_hrv_ms, 1)}` : ""],
            ["Resting HR", rhr ? `${num(rhr, 1)} bpm` : null, heart.average_resting_heart_rate ? `avg ${num(heart.average_resting_heart_rate, 1)}` : ""],
            ["Workouts", intText(workouts.workout_count ?? 0), recovery.latest_spo2 ? `SpO2 ${num(recovery.latest_spo2, 1)}%` : ""],
          ],
          evidenceTitle: "Positives",
          evidence: data.positives || [],
          secondaryTitle: "Watchouts",
          secondary: data.watchouts || [],
        };
      }

      function questionCluesModel(data) {
        const readiness = data.readiness || {};
        const metrics = data.relevant_metrics || [];
        const available = metrics.filter((item) => Number(item.records || 0) > 0);
        const intents = data.intent_hints || [];
        const freshness = data.data_freshness || {};
        const topMetrics = (available.length ? available : metrics).slice(0, 6);
        const hasSafetyFlags = (data.safety_flags || []).length > 0;
        return {
          accent: hasSafetyFlags ? "#a94f43" : "#4b6f8f",
          title: hasSafetyFlags ? "Health Check" : "Health Clues",
          eyebrow: hasSafetyFlags ? "Safety Context" : "Metric Finder",
          date: data.today?.activity_date && data.today?.recovery_date && data.today.activity_date !== data.today.recovery_date
            ? `Activity ${data.today.activity_date}; recovery ${data.today.recovery_date}`
            : data.today?.activity_date || freshness.latest_observed_date || "",
          chips: [
            titleCase(intents[0] || "overview"),
            `${available.length}/${metrics.length || 0} metrics`,
            freshnessChip(freshness),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: data.headline || "Useful Fitbit signals selected for this question.",
          focusTitle: hasSafetyFlags ? "Safety First" : "Best Clues",
          focus: hasSafetyFlags ? data.safety_flags || [] : data.clues || [],
          metrics: topMetrics.map((item) => [
            item.label || item.id,
            intText(item.records ?? 0),
            item.latest_observed_date || "not synced",
          ]),
          evidenceTitle: hasSafetyFlags ? "Relevant Metrics" : "Why These",
          evidence: topMetrics.map((item) => `${item.label || item.id}: ${item.reason || "Useful context."}`),
          secondaryTitle: hasSafetyFlags ? "Data Clues" : "Watchouts",
          secondary: hasSafetyFlags ? data.clues || [] : data.watchouts || [],
        };
      }

      function recoveryComparisonModel(data) {
        const readiness = data.readiness || {};
        const latest = data.latest || {};
        const baseline = data.baseline || {};
        const deltas = data.current_vs_baseline || {};
        const label = readiness.label || "pending";
        return {
          accent: readinessAccent(label),
          title: "Recovery Comparison",
          eyebrow: "Sleep + Heart",
          date: data.date_range?.start && data.date_range?.end ? `${data.date_range.start} to ${data.date_range.end}` : latest.date || "",
          chips: [
            label,
            `${data.data_used?.days_compared || data.window_days || 14} days`,
            freshnessChip(data.data_freshness || {}),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: data.headline || "Sleep, heart, and load compared against baseline.",
          focusTitle: "Pattern",
          focus: data.insights || [],
          metrics: [
            ["Sleep", latest.sleep_hours != null ? `${num(latest.sleep_hours, 1)}h` : null, baseline.sleep_hours != null ? `base ${num(baseline.sleep_hours, 1)}h` : ""],
            ["Sleep delta", deltas.sleep_hours_delta != null ? `${signed(deltas.sleep_hours_delta)}h` : null],
            ["HRV", latest.hrv_ms != null ? `${num(latest.hrv_ms, 1)} ms` : null, baseline.hrv_ms != null ? `base ${num(baseline.hrv_ms, 1)}` : ""],
            ["HRV delta", deltas.hrv_percent_delta != null ? `${signed(deltas.hrv_percent_delta)}%` : null],
            ["Resting HR", latest.resting_heart_rate != null ? `${latest.resting_heart_rate} bpm` : null, baseline.resting_heart_rate != null ? `base ${num(baseline.resting_heart_rate, 1)}` : ""],
            ["Load", latest.active_zone_minutes != null ? `${latest.active_zone_minutes} AZM` : null, baseline.active_zone_minutes != null ? `base ${num(baseline.active_zone_minutes, 1)}` : ""],
          ],
          evidenceTitle: "Positives",
          evidence: data.positives || [],
          secondaryTitle: "Watchouts",
          secondary: data.watchouts || [],
        };
      }

      function todayWorkoutModel(data) {
        const readiness = data.readiness || {};
        const label = readiness.label || data.data_used?.readiness_label || "pending";
        const today = data.today || {};
        const sleep = today.sleep || {};
        const goal = data.goal_context || {};
        const subjective = data.subjective_context || {};
        const freshness = data.data_freshness || {};
        const sleepHours = data.data_used?.latest_sleep_hours ?? sleep.asleep_hours ?? sleep.duration_hours;
        const goalDetail = goal.remaining_sessions != null
          ? `${goal.remaining_sessions} goal sessions left`
          : goal.target || "";
        return {
          accent: readinessAccent(label),
          title: "Today's Workout",
          eyebrow: "Coach Recommendation",
          date: data.activity_date && data.recovery_date && data.activity_date !== data.recovery_date
            ? `Activity ${data.activity_date}; recovery ${data.recovery_date}`
            : data.activity_date || data.latest_date || "",
          chips: [
            data.intensity,
            data.rpe_cap != null ? `RPE ${data.rpe_cap}` : "",
            label,
            freshnessChip(freshness),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: data.recommendation || readiness.recommendation || "Workout guidance ready.",
          focusTitle: "Do Today",
          focus: data.next_actions || [],
          metrics: [
            ["Steps", intText(today.steps ?? data.data_used?.steps_today ?? 0), "today"],
            ["Zone min", intText(today.active_zone_minutes ?? data.data_used?.active_zone_minutes_today ?? 0), "today"],
            ["Sleep", sleepHours ? `${num(sleepHours, 1)}h` : null],
            ["HRV", data.data_used?.hrv_ms ? `${num(data.data_used.hrv_ms, 1)} ms` : null],
            ["Soreness", subjective.soreness != null ? `${subjective.soreness}/10` : null, subjective.energy != null ? `energy ${subjective.energy}/10` : ""],
            ["Goal", goal.remaining_sessions != null ? intText(goal.remaining_sessions) : "No goal", goalDetail],
          ],
          evidenceTitle: "Why",
          evidence: prioritizeWorkoutEvidence(data.evidence || data.why || []),
          secondaryTitle: "Avoid",
          secondary: data.avoid || [],
        };
      }

      function prioritizeWorkoutEvidence(items) {
        const source = (items || []).filter(Boolean);
        const prioritized = [];
        const add = (item) => {
          if (item && !prioritized.includes(item)) prioritized.push(item);
        };
        const findByTerms = (terms) => {
          for (const term of terms) {
            const found = source.find((item) => item.toLowerCase().includes(term));
            if (found) return found;
          }
          return null;
        };

        add(findByTerms(["data freshness"]));
        add(findByTerms(["latest sleep", "sleep is"]));
        add(findByTerms(["hrv", "resting heart rate"]));
        add(findByTerms(["latest training load", "active zone minutes"]));
        add(findByTerms(["soreness check-in", "energy check-in", "stress check-in"]));
        add(findByTerms(["goal progress", "current goal"]));
        for (const item of source) add(item);
        return prioritized;
      }

      function readinessModel(data) {
        const context = data.context || (data.today ? data : {}) || {};
        const readiness = data.readiness || context.readiness || {};
        const today = data.today || context.today || {};
        const sleep = today.sleep || {};
        const heart = today.heart || {};
        const label = readiness.label || "pending";
        const score = finiteNumber(readiness.score, 0);
        const activityDate = context.activity_date || today.activity_date || context.latest_date || data.latest_date;
        const recoveryDate = context.recovery_date || today.recovery_date || activityDate;
        const latestLoad = today.latest_training_load || {};
        const sleepHours = sleep.asleep_hours ?? sleep.duration_hours;
        const source = activityDate && recoveryDate && activityDate !== recoveryDate
          ? `Activity ${activityDate}; recovery ${recoveryDate}.`
          : activityDate ? `Health context from ${activityDate}.` : "Waiting for synced health context.";
        return {
          accent: readinessAccent(label),
          title: "Readiness",
          eyebrow: "Mehair Coach",
          date: source,
          chips: [label, activityDate].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: readiness.recommendation || data.recommendation || "Health context synced.",
          focusTitle: "Coach Take",
          focus: [readiness.recommendation || data.recommendation || "Health context synced."],
          metrics: [
            ["Steps", intText(today.steps ?? 0)],
            ["Zone min", intText(today.active_zone_minutes ?? 0), latestLoad.date && latestLoad.date !== activityDate ? `${latestLoad.active_zone_minutes ?? 0} on ${latestLoad.date}` : ""],
            ["Active", optionalInt(today.active_minutes), "minutes"],
            ["Sleep", sleepHours ? `${num(sleepHours, 1)}h` : null, sleep.sessions_count ? `${sleep.sessions_count} sessions` : ""],
            ["Resting HR", today.resting_heart_rate ? `${today.resting_heart_rate} bpm` : heart.avg_bpm ? `${heart.avg_bpm} avg` : null],
            ["HRV", today.hrv_ms ? `${num(today.hrv_ms, 1)} ms` : null],
          ],
          evidenceTitle: "Evidence",
          evidence: readiness.evidence || data.evidence || [],
        };
      }

      function workoutPlanModel(data) {
        const readiness = data.readiness || {};
        const label = readiness.label || data.data_used?.readiness_label || "pending";
        const dataUsed = data.data_used || {};
        const planFocus = [
          ...(data.session_guidance || []).slice(0, 3),
          ...(data.focus || []).slice(0, 2),
        ];
        return {
          accent: readinessAccent(label),
          title: data.planned_activity || "Workout Plan",
          eyebrow: "Workout Plan",
          date: data.planned_date ? `Planned for ${data.planned_date}` : "Next planned session",
          chips: [data.recommended_intensity, `RPE ${data.rpe_cap || "?"}`, label].filter(Boolean),
          score: finiteNumber(readiness.score ?? dataUsed.readiness_score, 0),
          primaryLabel: "Readiness",
          headline: data.summary || "Workout adjusted to your synced health context.",
          focusTitle: "Session",
          focus: planFocus,
          metrics: [
            ["RPE cap", data.rpe_cap != null ? `${data.rpe_cap}/10` : null],
            ["Intensity", titleCase(data.recommended_intensity || "")],
            ["Sleep", dataUsed.sleep_asleep_hours ? `${num(dataUsed.sleep_asleep_hours, 1)}h` : null, dataUsed.sleep_sessions ? `${dataUsed.sleep_sessions} sessions` : ""],
            ["HRV", dataUsed.hrv_ms ? `${num(dataUsed.hrv_ms, 1)} ms` : null],
            ["Resting HR", dataUsed.resting_heart_rate ? `${dataUsed.resting_heart_rate} bpm` : null],
            ["Latest load", dataUsed.latest_training_load?.active_zone_minutes != null ? `${dataUsed.latest_training_load.active_zone_minutes} AZM` : null, dataUsed.latest_training_load?.date || ""],
          ],
          evidenceTitle: "Limits",
          evidence: (data.limiting_factors || data.why || []).slice(0, 5),
          secondaryTitle: "Avoid",
          secondary: (data.avoid || []).slice(0, 4),
        };
      }

      function sleepModel(data) {
        const latest = data.latest || {};
        const stages = latest.stages_minutes || {};
        const asleep = latest.asleep_hours ?? latest.duration_hours;
        const sessions = latest.sessions_count || 1;
        const delta = data.summary?.latest_vs_average_hours;
        const evidence = [];
        if (delta != null) evidence.push(`Latest sleep is ${Math.abs(delta)}h ${delta < 0 ? "below" : "above"} recent average.`);
        if (latest.awake_minutes != null) evidence.push(`${latest.awake_minutes} minutes awake during the sleep window.`);
        if (stages.deep != null || stages.rem != null) evidence.push(`Deep ${num(stages.deep, 0)}m and REM ${num(stages.rem, 0)}m were detected.`);
        return {
          accent: "#386f8f",
          title: "Sleep",
          eyebrow: "Recovery",
          date: latest.date ? `Latest sleep from ${latest.date}` : "Latest synced sleep",
          chips: [`${sessions} session${sessions === 1 ? "" : "s"}`],
          score: asleep ? Math.min(100, Math.round((asleep / 8) * 100)) : 0,
          primaryLabel: "Sleep target",
          headline: sessions > 1 ? "Split sleep was combined for coaching." : "Sleep session captured.",
          focusTitle: "Sleep Context",
          focus: evidence.slice(0, 3),
          metrics: [
            ["Asleep", asleep ? `${num(asleep, 1)}h` : null],
            ["Duration", latest.duration_hours ? `${num(latest.duration_hours, 1)}h` : null],
            ["Awake", latest.awake_minutes != null ? `${latest.awake_minutes}m` : null],
            ["Deep", stages.deep != null ? `${num(stages.deep, 0)}m` : null],
            ["REM", stages.rem != null ? `${num(stages.rem, 0)}m` : null],
            ["Average", data.summary?.average_asleep_hours ? `${num(data.summary.average_asleep_hours, 1)}h` : null],
          ],
          evidenceTitle: "Evidence",
          evidence,
        };
      }

      function activityModel(data) {
        const totals = data.totals || {};
        const highest = data.highest_load_day || {};
        const days = data.days || [];
        return {
          accent: "#7a6a18",
          title: "Activity Load",
          eyebrow: "Training",
          date: rangeText(days),
          chips: [`${days.length || 0} days`],
          score: clamp(Math.round((Number(totals.active_zone_minutes || highest.active_zone_minutes || 0) / 150) * 100), 0, 100),
          primaryLabel: "Load",
          headline: `${intText(totals.steps ?? 0)} steps across the queried window.`,
          focusTitle: "Load Context",
          focus: highest.date ? [`${highest.date} had the highest zone-minute load in this window.`] : ["Latest synced activity load."],
          metrics: [
            ["Steps", intText(totals.steps ?? 0)],
            ["Active", intText(totals.active_minutes ?? 0), "minutes"],
            ["Zone min", intText(totals.active_zone_minutes ?? 0)],
            ["Highest AZM", highest.active_zone_minutes != null ? intText(highest.active_zone_minutes) : null, highest.date || ""],
            ["Latest day", days.length ? days[days.length - 1].date : null],
            ["Distance", sumDistance(days)],
          ],
          evidenceTitle: "Evidence",
          evidence: highest.date ? [`${highest.date} was the highest load day.`] : [],
        };
      }

      function heartModel(data) {
        const days = data.days || [];
        const latest = data.latest || days[days.length - 1] || {};
        const summary = data.summary || {};
        const score = latest.hrv_ms && summary.average_hrv_ms
          ? clamp(Math.round((latest.hrv_ms / summary.average_hrv_ms) * 75), 0, 100)
          : 50;
        return {
          accent: "#8a4b3e",
          title: "Heart Trends",
          eyebrow: "Recovery",
          date: latest.date || rangeText(days),
          chips: ["heart", days.length ? `${days.length} days` : ""].filter(Boolean),
          score,
          primaryLabel: latest.hrv_ms != null ? "HRV vs avg" : "Heart",
          headline: "Recent HRV and resting heart-rate context.",
          focusTitle: "Heart Context",
          focus: [
            summary.average_hrv_ms != null ? `Average HRV is ${num(summary.average_hrv_ms, 1)} ms.` : null,
            summary.average_resting_bpm != null ? `Average resting HR is ${num(summary.average_resting_bpm, 1)} bpm.` : null,
          ].filter(Boolean),
          metrics: [
            ["Latest HRV", latest.hrv_ms != null ? `${num(latest.hrv_ms, 1)} ms` : null],
            ["Avg HRV", summary.average_hrv_ms != null ? `${num(summary.average_hrv_ms, 1)} ms` : null],
            ["Resting HR", latest.resting_bpm != null ? `${latest.resting_bpm} bpm` : null],
            ["Avg RHR", summary.average_resting_bpm != null ? `${num(summary.average_resting_bpm, 1)} bpm` : null],
            ["Avg BPM", latest.avg_bpm != null ? `${num(latest.avg_bpm, 1)} bpm` : null],
            ["Days", intText(days.length || 0)],
          ],
          evidenceTitle: "Evidence",
          evidence: [
            summary.average_hrv_ms != null ? `Average HRV: ${num(summary.average_hrv_ms, 1)} ms.` : null,
            summary.average_resting_bpm != null ? `Average resting HR: ${num(summary.average_resting_bpm, 1)} bpm.` : null,
          ].filter(Boolean),
        };
      }

      function metricQueryModel(data) {
        const metrics = data.metrics || {};
        const entries = Object.entries(metrics);
        return {
          accent: "#4b6f8f",
          title: "Metric Query",
          eyebrow: "Data",
          date: data.start_date && data.end_date ? `${data.start_date} to ${data.end_date}` : "",
          chips: [`${data.requested_metrics.length} metrics`, data.source || ""].filter(Boolean),
          score: clamp(Number(data.record_count || 0), 0, 100),
          primaryLabel: "Records",
          headline: "Synced local health metrics returned for this window.",
          focusTitle: "Returned Metrics",
          focus: entries.slice(0, 5).map(([id, item]) => `${item.catalog?.label || id}: ${item.record_count || 0} records`),
          metrics: entries.slice(0, 6).map(([id, item]) => [
            item.catalog?.label || id,
            intText(item.record_count ?? 0),
            item.latest_observed_date || "",
          ]),
          evidenceTitle: "Gaps",
          evidence: [
            data.missing_metrics?.length ? `No records in range for: ${data.missing_metrics.join(", ")}.` : null,
            data.unknown_metrics?.length ? `Unsupported metrics ignored: ${data.unknown_metrics.join(", ")}.` : null,
          ].filter(Boolean),
        };
      }

      function renderModel(model) {
        const accent = model.accent || "#39745c";
        root.style.setProperty("--accent", accent);
        root.style.setProperty("--accent-soft", softFor(accent));
        const score = clamp(Math.round(Number(model.score || 0)), 0, 100);
        root.style.setProperty("--score", String(score));
        const primaryFocus = listItems(model.focus, "Health context synced.");
        const secondaryTitle = model.secondaryTitle || "Evidence";
        const secondary = model.secondary || model.evidence || [];
        root.innerHTML = `
          <div class="mast">
            <div class="identity">
              <p class="eyebrow">${escapeHtml(model.eyebrow || "Mehair Coach")}</p>
              <h1>${escapeHtml(model.title || "Mehair Coach")}</h1>
              <p class="headline">${escapeHtml(model.headline || "Health context synced.")}</p>
            </div>
            <div class="stamp">${escapeHtml(model.date || "")}</div>
          </div>
          <div class="status-row">
            ${(model.chips || ["health"]).slice(0, 4).map((item, index) => `<span class="chip ${index === 0 ? "accent" : ""}">${escapeHtml(item)}</span>`).join("")}
          </div>
          <div class="hero">
            <div class="gauge" aria-label="${escapeHtml(model.primaryLabel || "score")} ${score}">
              <div class="gauge-inner">
                <b>${escapeHtml(score)}</b>
                <span>${escapeHtml(model.primaryLabel || "Score")}</span>
              </div>
            </div>
            <div class="plan-box">
              <h2>${escapeHtml(model.focusTitle || "Coach Take")}</h2>
              <ul class="focus-list">${primaryFocus}</ul>
            </div>
          </div>
          <div class="metrics">
            ${(model.metrics || []).slice(0, 6).map((item) => metric(item[0], item[1], item[2])).join("")}
          </div>
          <div class="details">
            <div class="section">
              <h3>${escapeHtml(model.evidenceTitle || "Evidence")}</h3>
              <ul class="evidence">${listItems(model.evidence, "More synced Fitbit data will make this richer.")}</ul>
            </div>
            <div class="section">
              <h3>${escapeHtml(secondaryTitle)}</h3>
              <ul class="evidence">${listItems(secondary, "No extra limits detected.")}</ul>
            </div>
          </div>
        `;
      }

      function metric(label, value, detail) {
        const detailHtml = detail ? `<small>${escapeHtml(detail)}</small>` : "";
        return `<div class="metric"><b>${escapeHtml(value ?? "No data")}</b><span>${escapeHtml(label)}</span>${detailHtml}</div>`;
      }

      function freshnessChip(freshness) {
        if (!freshness || !freshness.freshness_level) return "";
        if (freshness.freshness_level === "fresh") return "fresh today";
        if (freshness.freshness_level === "aging") return "sync if needed";
        if (freshness.freshness_level === "stale") return "sync recommended";
        return "sync status unknown";
      }

      function listItems(items, fallback) {
        const usable = (items || []).filter(Boolean).slice(0, 5);
        const content = usable.length ? usable : [fallback];
        return content.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      }

      function readinessAccent(label) {
        if (label === "green") return "#39745c";
        if (label === "yellow") return "#9b741c";
        if (label === "red") return "#a94f43";
        return "#667078";
      }

      function softFor(accent) {
        const map = {
          "#39745c": "#edf5f0",
          "#9b741c": "#fbf5e7",
          "#a94f43": "#fbefed",
          "#386f8f": "#edf5fa",
          "#7a6a18": "#f8f4df",
          "#8a4b3e": "#f7efed",
          "#4b6f8f": "#eef4fa",
        };
        return map[accent] || "#f1f3f4";
      }

      function finiteNumber(value, fallback) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
      }

      function clamp(value, min, max) {
        const number = Number(value);
        if (!Number.isFinite(number)) return min;
        return Math.max(min, Math.min(max, number));
      }

      function num(value, digits) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        return number.toFixed(digits).replace(/\\.0$/, "");
      }

      function intText(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        return Math.round(number).toLocaleString();
      }

      function signed(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "";
        return `${number >= 0 ? "+" : ""}${num(number, Math.abs(number) < 10 ? 1 : 0)}`;
      }

      function optionalInt(value) {
        if (value == null) return null;
        return intText(value);
      }

      function rangeText(days) {
        if (!days || !days.length) return "";
        return `${days[0].date} to ${days[days.length - 1].date}`;
      }

      function sumDistance(days) {
        const km = (days || []).reduce((total, day) => total + Number(day.distance_km || 0), 0);
        return km ? `${num(km, 1)} km` : null;
      }

      function titleCase(value) {
        return String(value)
          .split(/[-_\\s]+/)
          .filter(Boolean)
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(" ");
      }

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }

      render();
      initialize();
    </script>
  </body>
</html>
""".strip()


WIDGET_PREVIEW_STATES: dict[str, dict] = {
    "health-clues": {
        "status": "ok",
        "clue_type": "health_question_clues",
        "question": "I feel cooked today. Which metrics matter?",
        "headline": "Latest recovery comparison: sleep 5.1h (-2.2h); HRV 36.0 ms (-36%); RHR 67 bpm (+9.5).",
        "intent_hints": ["workout_decision", "recovery", "sleep", "heart", "activity_load"],
        "relevant_metrics": [
            {
                "id": "sleep",
                "label": "Sleep",
                "records": 4,
                "latest_observed_date": "2026-07-03",
                "reason": "Sleep duration, timing, and stages are primary recovery and fatigue context.",
            },
            {
                "id": "daily-heart-rate-variability",
                "label": "Daily HRV",
                "records": 4,
                "latest_observed_date": "2026-07-03",
                "reason": "Daily HRV helps spot autonomic recovery changes versus baseline.",
            },
            {
                "id": "daily-resting-heart-rate",
                "label": "Resting heart rate",
                "records": 4,
                "latest_observed_date": "2026-07-03",
                "reason": "Resting heart rate often rises with stress, fatigue, illness, or under-recovery.",
            },
            {
                "id": "active-zone-minutes",
                "label": "Active Zone Minutes",
                "records": 3,
                "latest_observed_date": "2026-07-02",
                "reason": "Active Zone Minutes are a compact Fitbit load signal for workout decisions.",
            },
        ],
        "clues": [
            "Readiness is red at 38/100.",
            "Latest energy check-in is 3/10.",
            "Latest soreness check-in is 7/10.",
            "Latest sleep is short at 5.1h.",
            "HRV is 36% below recent baseline.",
            "Goal progress in this window: 1/4 workout sessions logged.",
        ],
        "watchouts": [
            "Low self-reported energy supports a conservative training call.",
            "High soreness should cap intensity and avoid loading sore areas.",
            "Sleep is short while HRV is suppressed or resting heart rate is elevated.",
            "High zone-minute load can suppress HRV or elevate resting heart rate.",
        ],
        "positives": ["The comparison has enough data to ground the recovery discussion."],
        "personal_context": {
            "goal": {"goal": {"target": "Train four days per week", "days_per_week": 4}},
            "recent_checkins": [
                {"checkin": {"energy": 3, "soreness": 7, "stress": 6, "notes": "Legs heavy after squash"}}
            ],
        },
        "data_used": {
            "goal_present": True,
            "recent_checkins_count": 1,
            "recent_workout_count": 1,
        },
        "readiness": {
            "score": 38,
            "label": "red",
            "recommendation": "Prioritize recovery, mobility, walking, and sleep.",
        },
        "today": {
            "activity_date": "2026-07-03",
            "recovery_date": "2026-07-03",
            "steps": 1600,
            "sleep_hours": 5.1,
            "hrv_ms": 36,
            "resting_heart_rate": 67,
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 72},
        },
        "data_freshness": {"freshness_level": "fresh", "latest_observed_date": "2026-07-03"},
    },
    "today-workout": {
        "status": "ok",
        "intensity": "easy",
        "rpe_cap": 6,
        "recommendation": "Make today recovery-biased: walking, mobility, breath work, and an earlier bedtime. Your soreness check-in is high at 7/10, so bias toward recovery or pain-free technique.",
        "next_actions": [
            "Make today recovery-biased: walk, mobility, easy cardio, or rest.",
            "You are 2 session(s) from the weekly target, but recovery signals make an easy day smarter.",
            "Protect sleep tonight and reassess after the next sync.",
        ],
        "avoid": ["Loading sore areas aggressively", "Another hard conditioning block today"],
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "today": {
            "steps": 1600,
            "active_zone_minutes": 0,
            "sleep": {"asleep_hours": 5.1, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 72},
        },
        "data_used": {
            "latest_sleep_hours": 5.1,
            "hrv_ms": 36,
            "resting_heart_rate": 67,
        },
        "readiness": {
            "score": 38,
            "label": "red",
            "evidence": [
                "Latest sleep is short at 5.1h.",
                "HRV is below recent baseline: 36.0 ms vs 56.5 ms.",
                "Resting heart rate is elevated: 67 bpm vs 58 bpm baseline.",
            ],
        },
        "evidence": [
            "Latest sleep is short at 5.1h.",
            "HRV is below recent baseline: 36.0 ms vs 56.5 ms.",
            "Resting heart rate is elevated: 67 bpm vs 58 bpm baseline.",
            "Latest training load: 72 Active Zone Minutes on 2026-07-02.",
            "Latest energy check-in is 3/10.",
            "Latest soreness check-in is 7/10.",
            "Goal progress: 2/4 sessions logged; 2 remaining.",
            "Hardest recent workout: Squash match (72 Active Zone Minutes, 2026-07-02).",
        ],
        "goal_context": {
            "target": "Train four days per week",
            "days_per_week": 4,
            "recent_workouts": 2,
            "remaining_sessions": 2,
        },
        "subjective_context": {"energy": 3, "soreness": 7, "stress": 6},
        "data_freshness": {"freshness_level": "fresh", "latest_observed_date": "2026-07-03"},
    },
    "recovery-comparison": {
        "status": "ok",
        "comparison_type": "sleep_heart_recovery",
        "headline": "Latest recovery comparison: sleep 5.1h (-2.2h); HRV 36.0 ms (-36%); RHR 67 bpm (+9.5).",
        "date_range": {"start": "2026-06-30", "end": "2026-07-03"},
        "window_days": 7,
        "latest": {
            "date": "2026-07-03",
            "sleep_hours": 5.1,
            "hrv_ms": 36,
            "resting_heart_rate": 67,
            "active_zone_minutes": 0,
        },
        "baseline": {
            "sleep_hours": 7.3,
            "hrv_ms": 56.5,
            "resting_heart_rate": 57.5,
            "active_zone_minutes": 42,
        },
        "current_vs_baseline": {
            "sleep_hours_delta": -2.2,
            "hrv_percent_delta": -36.3,
            "resting_heart_rate_delta": 9.5,
        },
        "insights": [
            "Short sleep is lining up with weaker heart recovery signals.",
            "Recent training load is high at 72 zone minutes.",
        ],
        "positives": ["Enough sleep and heart data is available to compare against baseline."],
        "watchouts": [
            "Sleep is short while HRV is suppressed or resting heart rate is elevated.",
            "High zone-minute load can suppress HRV or elevate resting heart rate.",
        ],
        "readiness": {"score": 38, "label": "red"},
        "data_used": {"days_compared": 4},
        "data_freshness": {"freshness_level": "fresh"},
    },
    "heart-safety": {
        "status": "ok",
        "clue_type": "health_question_clues",
        "question": "Should I worry about my high heart rate and dizziness?",
        "headline": "Use heart, HRV, resting heart rate, sleep, and symptoms carefully; wearable data cannot diagnose.",
        "intent_hints": ["heart", "recovery"],
        "relevant_metrics": [
            {
                "id": "daily-resting-heart-rate",
                "label": "Resting heart rate",
                "records": 3,
                "latest_observed_date": "2026-07-03",
                "reason": "Resting heart rate often rises with stress, fatigue, illness, or under-recovery.",
            },
            {
                "id": "heart-rate",
                "label": "Heart rate",
                "records": 24,
                "latest_observed_date": "2026-07-03",
                "reason": "Heart-rate samples help explain intensity, unusual spikes, and workout effort.",
            },
            {
                "id": "daily-heart-rate-variability",
                "label": "Daily HRV",
                "records": 3,
                "latest_observed_date": "2026-07-03",
                "reason": "Daily HRV helps spot autonomic recovery changes versus baseline.",
            },
        ],
        "clues": [
            "Readiness is yellow at 55/100.",
            "Latest resting heart rate is 92 bpm.",
            "HRV is below recent baseline.",
        ],
        "watchouts": [
            "The question mentions symptoms or heart concerns that need medical caution; do not diagnose from wearable data and recommend urgent care for severe, new, or worsening symptoms.",
            "Latest resting heart rate is high at 92 bpm, so avoid hard training advice without caution and context.",
        ],
        "safety_flags": [
            "The question mentions symptoms or heart concerns that need medical caution; do not diagnose from wearable data and recommend urgent care for severe, new, or worsening symptoms."
        ],
        "readiness": {"score": 55, "label": "yellow"},
        "today": {"activity_date": "2026-07-03", "recovery_date": "2026-07-03"},
        "data_freshness": {"freshness_level": "fresh", "latest_observed_date": "2026-07-03"},
    },
}


def widget_preview_html(state: str = "health-clues") -> str:
    preview_state = state if state in WIDGET_PREVIEW_STATES else "health-clues"
    data = json.dumps(WIDGET_PREVIEW_STATES[preview_state])
    injection = f"""
      state.data = {data};
      render();
    """
    return TODAY_WIDGET_HTML.replace("      render();\n      initialize();", injection.rstrip())
