from __future__ import annotations

import json


WIDGET_URI = "ui://mehair/today-v8.html"
LEGACY_WIDGET_URIS = (
    "ui://mehair/today-v1.html",
    "ui://mehair/today-v2.html",
    "ui://mehair/today-v3.html",
    "ui://mehair/today-v4.html",
    "ui://mehair/today-v5.html",
    "ui://mehair/today-v6.html",
    "ui://mehair/today-v7.html",
)
WIDGET_RESOURCE_URIS = (WIDGET_URI, *LEGACY_WIDGET_URIS)
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
        max-width: 100%;
        border: 1px solid #d9e1dc;
        border-radius: 999px;
        background: #fff;
        color: #313940;
        font-size: 12px;
        font-weight: 720;
        line-height: 1.15;
        padding: 5px 9px;
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

      .workout-blocks {
        display: grid;
        gap: 8px;
        border-top: 1px solid #edf0ea;
        padding: 0 14px 14px;
      }

      .workout-block {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 5px 10px;
        align-items: start;
        border: 1px solid #e4e9e4;
        border-radius: 8px;
        background: #fbfcfb;
        padding: 10px;
      }

      .workout-block b {
        min-width: 0;
        color: #20272e;
        font-size: 13px;
        font-weight: 820;
        line-height: 1.2;
      }

      .workout-block span {
        color: var(--accent);
        font-size: 12px;
        font-weight: 780;
        line-height: 1.2;
        white-space: nowrap;
      }

      .workout-block small {
        grid-column: 1 / -1;
        color: #59636b;
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
        min-height: 92px;
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

      .metric em {
        display: block;
        margin-top: 5px;
        color: #4b565e;
        font-size: 11px;
        font-style: normal;
        line-height: 1.28;
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
        .workout-block { grid-template-columns: 1fr; }
        .workout-block span { white-space: normal; }
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
          <span>Preparing health card...</span>
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
            appInfo: { name: "mehair-coach-widget", version: "0.4.0" },
            appCapabilities: {},
            protocolVersion: "2026-01-26",
          });
          rpcNotify("ui/notifications/initialized", {});
        } catch (error) {
          console.error(error);
        }
      }

      function render() {
        if (!hasCardData(state.data)) {
          renderEmpty("Preparing the health card from the latest tool result.", "waiting");
          return;
        }
        const data = state.data;
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
        const title = status === "empty"
          ? "No synced data yet"
          : status === "waiting"
            ? "Preparing card"
            : "Setup needed";
        root.innerHTML = `
          <div class="empty">
            <strong>${escapeHtml(title)}</strong>
            <span>${escapeHtml(message)}</span>
          </div>
        `;
      }

      function hasCardData(data) {
        if (!data || typeof data !== "object") return false;
        const keys = Object.keys(data).filter((key) => key !== "status");
        if (!keys.length) return false;
        return Boolean(
          data.readiness ||
          data.today ||
          data.sections ||
          data.guidance_type ||
          data.planned_activity ||
          data.recommendation ||
          data.latest ||
          data.totals ||
          data.summary ||
          data.metrics ||
          data.clue_type ||
          data.comparison_type ||
          data.requested_metrics
        );
      }

      function toViewModel(data) {
        if (data?.overview_type === "health_overview" && data?.sections) return healthOverviewModel(data);
        if (data?.clue_type === "health_question_clues") return questionCluesModel(data);
        if (data?.comparison_type === "sleep_heart_recovery") return recoveryComparisonModel(data);
        if (data?.guidance_type === "active_workout_guidance") return activeWorkoutModel(data);
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
        const brief = data.daily_brief || {};
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
        const today = data.today || {};
        const latestActivity = activity.latest || {};
        const latestLoad = today.latest_training_load || activity.highest_load_day || {};
        const sleepHours = sleep.latest_asleep_hours ?? data.today?.sleep?.asleep_hours ?? data.today?.sleep?.duration_hours;
        const hrv = heart.latest_hrv_ms ?? data.today?.hrv_ms;
        const rhr = heart.latest_resting_heart_rate ?? data.today?.resting_heart_rate;
        const todaySteps = today.steps ?? latestActivity.steps;
        const windowSteps = activity.totals?.steps;
        const latestLoadAzm = latestLoad.active_zone_minutes ?? today.active_zone_minutes ?? latestActivity.active_zone_minutes;
        const latestLoadDetail = latestLoad.date ? `latest ${latestLoad.date}` : (range ? `window ${range}` : "latest");
        const sleepDelta = sleep.latest_vs_average_hours;
        const hrvDelta = hrv != null && heart.average_hrv_ms ? ((Number(hrv) - Number(heart.average_hrv_ms)) / Number(heart.average_hrv_ms)) * 100 : null;
        const rhrDelta = rhr != null && heart.average_resting_heart_rate ? Number(rhr) - Number(heart.average_resting_heart_rate) : null;
        const vitalsValue = recovery.latest_spo2 != null
          ? `${num(recovery.latest_spo2, 1)}%`
          : recovery.latest_respiratory_rate != null
            ? `${num(recovery.latest_respiratory_rate, 1)}`
            : null;
        const vitalsDetail = recovery.latest_spo2 != null
          ? `SpO2 ${recovery.latest_spo2_date || ""}`.trim()
          : recovery.latest_respiratory_rate != null
            ? `resp ${recovery.latest_respiratory_rate_date || ""}`.trim()
            : "";
        const primaryActions = (brief.today_plan || data.next_actions || []).slice(0, 4);
        const contextGaps = brief.context_gaps || [];
        const watchoutsAndGaps = [
          ...(data.watchouts || []),
          ...contextGaps.map((item) => `Context gap: ${item}`),
        ];
        const prioritySignals = (brief.priority_signals || []).map((item) => {
          const label = item.label || item.category || "Signal";
          const detail = item.detail || item.impact || "";
          return detail ? `${label}: ${detail}` : label;
        });
        return {
          accent: readinessAccent(label),
          title: "Health Overview",
          eyebrow: "Mehair Coach",
          date: range || data.data_freshness?.latest_observed_date || "",
          chips: [
            readinessChip(label),
            brief.training_bias ? titleCase(brief.training_bias) : "",
            `${dataUsed.synced_metric_count || 0} metrics`,
            freshnessChip(freshness),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: brief.summary || data.headline || readiness.recommendation || "All synced health data summarized.",
          focusTitle: "Today Plan",
          focus: primaryActions,
          metrics: [
            ["Move Today", todaySteps != null ? intText(todaySteps) : null, windowSteps != null && range ? `${intText(windowSteps)} in window` : latestActivity.date || ""],
            ["Training Load", latestLoadAzm != null ? `${intText(latestLoadAzm)} AZM` : null, latestLoadDetail, "AZM = Fitbit hard-work minutes."],
            ["Sleep vs Avg", sleepDelta != null ? `${signed(sleepDelta)}h` : (sleepHours != null ? `${num(sleepHours, 1)}h` : null), sleepHours != null ? `latest ${num(sleepHours, 1)}h` : ""],
            ["HRV vs Avg", hrvDelta != null ? `${signed(hrvDelta)}%` : (hrv != null ? `${num(hrv, 1)} ms` : null), hrv != null && heart.average_hrv_ms ? `${num(hrv, 1)} vs ${num(heart.average_hrv_ms, 1)} ms` : "", "HRV = recovery stress signal."],
            ["RHR vs Avg", rhrDelta != null ? `${signed(rhrDelta)} bpm` : (rhr != null ? `${num(rhr, 1)} bpm` : null), rhr != null && heart.average_resting_heart_rate ? `${num(rhr, 0)} vs ${num(heart.average_resting_heart_rate, 0)} bpm` : "", "RHR = resting heart rate."],
            workouts.workout_count > 0
              ? ["Workouts", intText(workouts.workout_count), range || "window"]
              : vitalsValue
                ? ["Vitals", vitalsValue, vitalsDetail]
                : ["Freshness", titleCase(freshness.freshness_level || "unknown"), freshness.latest_observed_date ? `latest ${freshness.latest_observed_date}` : ""],
          ],
          evidenceTitle: prioritySignals.length ? "Priority Signals" : "Positives",
          evidence: prioritySignals.length ? prioritySignals : data.positives || [],
          secondaryTitle: contextGaps.length ? "Watchouts & Gaps" : "Watchouts",
          secondary: watchoutsAndGaps,
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
        const coach = data.coach_response || {};
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
            intensityChip(data.intensity),
            rpeChip(data.rpe_cap),
            readinessChip(label),
            freshnessChip(freshness),
          ].filter(Boolean),
          score: finiteNumber(readiness.score, 0),
          primaryLabel: "Readiness",
          headline: coach.short_answer || workoutHeadline(data),
          focusTitle: "What To Do",
          focus: coach.what_to_do || data.next_actions || [],
          metrics: [
            ["Move Today", intText(today.steps ?? data.data_used?.steps_today ?? 0), "steps today", "Light movement context, not the whole decision."],
            ["AZM Today", intText(today.active_zone_minutes ?? data.data_used?.active_zone_minutes_today ?? 0), "today", "AZM = Fitbit hard-work minutes."],
            ["Sleep", sleepHours != null ? `${num(sleepHours, 1)}h` : null],
            ["HRV", data.data_used?.hrv_ms != null ? `${num(data.data_used.hrv_ms, 1)} ms` : null],
            ["Soreness", subjective.soreness != null ? `${subjective.soreness}/10` : null, subjective.energy != null ? `energy ${subjective.energy}/10` : ""],
            ["Goal", goal.remaining_sessions != null ? intText(goal.remaining_sessions) : "No goal", goalDetail],
          ],
          evidenceTitle: "Why",
          evidence: coach.why || prioritizeWorkoutEvidence(data.evidence || data.why || []),
          secondaryTitle: "Avoid",
          secondary: coach.avoid || data.avoid || [],
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
            ["Sleep", sleepHours != null ? `${num(sleepHours, 1)}h` : null, sleep.sessions_count ? `${sleep.sessions_count} sessions` : ""],
            ["Resting HR", today.resting_heart_rate ? `${today.resting_heart_rate} bpm` : heart.avg_bpm ? `${heart.avg_bpm} avg` : null],
            ["HRV", today.hrv_ms != null ? `${num(today.hrv_ms, 1)} ms` : null],
          ],
          evidenceTitle: "Evidence",
          evidence: readiness.evidence || data.evidence || [],
        };
      }

      function workoutPlanModel(data) {
        const readiness = data.readiness || {};
        const label = readiness.label || data.data_used?.readiness_label || "pending";
        const dataUsed = data.data_used || {};
        const coach = data.coach_response || {};
        const substitutions = data.substitutions || [];
        const planFocus = [
          ...(data.session_guidance || []).slice(0, 3),
          ...(data.focus || []).slice(0, 2),
        ];
        return {
          accent: readinessAccent(label),
          title: workoutTitle(data.planned_activity, data.recommended_intensity),
          eyebrow: "Workout Plan",
          date: data.planned_date ? `Planned for ${data.planned_date}` : "Next planned session",
          chips: [intensityChip(data.recommended_intensity), rpeChip(data.rpe_cap), readinessChip(label)].filter(Boolean),
          score: finiteNumber(readiness.score ?? dataUsed.readiness_score, 0),
          primaryLabel: "Readiness",
          headline: coach.short_answer || workoutHeadline(data),
          focusTitle: "What To Do",
          focus: coach.what_to_do || planFocus,
          blocks: data.exercise_blocks || [],
          metrics: [
            ["RPE cap", data.rpe_cap != null ? `${data.rpe_cap}/10` : null, rpePlain(data.rpe_cap)],
            ["Intensity", titleCase(data.recommended_intensity || ""), "", "The workout should feel this aggressive."],
            ["Sleep", dataUsed.sleep_asleep_hours != null ? `${num(dataUsed.sleep_asleep_hours, 1)}h` : null, dataUsed.sleep_sessions ? `${dataUsed.sleep_sessions} sessions` : ""],
            ["HRV", dataUsed.hrv_ms != null ? `${num(dataUsed.hrv_ms, 1)} ms` : null],
            ["Resting HR", dataUsed.resting_heart_rate ? `${dataUsed.resting_heart_rate} bpm` : null],
            ["Latest load", dataUsed.latest_training_load?.active_zone_minutes != null ? `${dataUsed.latest_training_load.active_zone_minutes} AZM` : null, dataUsed.latest_training_load?.date || "", "AZM = Fitbit hard-work minutes."],
          ],
          evidenceTitle: "Why This Plan",
          evidence: (coach.why || data.limiting_factors || data.why || []).slice(0, 5),
          secondaryTitle: substitutions.length ? "Substitutions" : "Avoid",
          secondary: (substitutions.length ? substitutions : coach.avoid || data.avoid || []).slice(0, 5),
        };
      }

      function activeWorkoutModel(data) {
        const readiness = data.readiness || {};
        const dataUsed = data.data_used || {};
        const live = data.live_inputs || {};
        const safety = data.safety_flags || [];
        const coach = data.coach_response || {};
        const evidence = coach.why || (safety.length ? safety : data.evidence || []);
        return {
          accent: safety.length ? "#a94f43" : readinessAccent(readiness.label || dataUsed.readiness_label),
          title: "Active Workout",
          eyebrow: data.planned_activity || "In-Session Check",
          date: live.elapsed_minutes != null ? `${live.elapsed_minutes} min elapsed` : data.activity_date || "",
          chips: [
            titleCase(data.decision || "guidance"),
            live.current_heart_rate_bpm != null ? `${live.current_heart_rate_bpm} bpm` : "",
            live.current_rpe != null ? rpeChip(live.current_rpe) : "",
            live.pain_level != null ? `Pain ${live.pain_level}/10` : "",
          ].filter(Boolean),
          score: finiteNumber(readiness.score ?? dataUsed.readiness_score, 0),
          primaryLabel: "Readiness",
          headline: coach.short_answer || data.headline || "Use live symptoms and effort to adjust the session.",
          focusTitle: "Do Now",
          focus: coach.what_to_do || data.immediate_actions || [],
          metrics: [
            ["Heart rate", live.current_heart_rate_bpm != null ? `${live.current_heart_rate_bpm} bpm` : null],
            ["RPE", live.current_rpe != null ? `${live.current_rpe}/10` : null, rpePlain(live.current_rpe)],
            ["Pain", live.pain_level != null ? `${live.pain_level}/10` : null],
            ["Elapsed", live.elapsed_minutes != null ? `${live.elapsed_minutes} min` : null],
            ["Readiness", readiness.label || dataUsed.readiness_label || null, readiness.label ? readinessChip(readiness.label) : ""],
            ["Latest load", dataUsed.latest_training_load?.active_zone_minutes != null ? `${dataUsed.latest_training_load.active_zone_minutes} AZM` : null, "", "AZM = Fitbit hard-work minutes."],
          ],
          evidenceTitle: safety.length ? "Safety Flags" : "Evidence",
          evidence,
          secondaryTitle: safety.length ? "Stop If" : "Modify / Avoid",
          secondary: (safety.length ? coach.stop_if || safety : [...(data.modifications || []), ...(coach.avoid || data.avoid || [])]).slice(0, 5),
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
        const blocks = renderBlocks(model.blocks);
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
          ${blocks}
          <div class="metrics">
            ${(model.metrics || []).slice(0, 6).map((item) => metric(item[0], item[1], item[2], item[3])).join("")}
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

      function metric(label, value, detail, explanation) {
        const detailHtml = detail ? `<small>${escapeHtml(detail)}</small>` : "";
        const explain = explanation || metricHint(label);
        const explainHtml = explain ? `<em>${escapeHtml(explain)}</em>` : "";
        return `<div class="metric"><b>${escapeHtml(value ?? "No data")}</b><span>${escapeHtml(label)}</span>${detailHtml}${explainHtml}</div>`;
      }

      function renderBlocks(blocks) {
        const usable = (blocks || []).filter(Boolean).slice(0, 6);
        if (!usable.length) return "";
        return `<div class="workout-blocks">${usable.map(workoutBlock).join("")}</div>`;
      }

      function workoutBlock(block) {
        if (typeof block === "string") {
          return `<div class="workout-block"><b>${escapeHtml(block)}</b></div>`;
        }
        const name = block.exercise || block.name || "Exercise";
        const prescription = [block.sets ? `${block.sets} sets` : "", block.reps || "", explainPrescription(block.intensity || "")]
          .filter(Boolean)
          .join(" | ");
        const note = [block.note || "", block.alternative ? `Alt: ${block.alternative}` : ""]
          .filter(Boolean)
          .join(" ");
        return `
          <div class="workout-block">
            <b>${escapeHtml(name)}</b>
            <span>${escapeHtml(prescription)}</span>
            ${note ? `<small>${escapeHtml(note)}</small>` : ""}
          </div>
        `;
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
        return content.map((item) => `<li>${escapeHtml(explainEvidenceItem(item))}</li>`).join("");
      }

      function intensityChip(value) {
        const label = titleCase(value || "guided");
        const lower = String(value || "").toLowerCase();
        if (lower.includes("easy")) return `${label}: recovery pace`;
        if (lower.includes("moderate-to-hard")) return `${label}: challenging`;
        if (lower.includes("moderate")) return `${label}: controlled`;
        return label;
      }

      function readinessChip(label) {
        const clean = titleCase(label || "pending");
        const lower = String(label || "").toLowerCase();
        if (lower === "green") return `${clean}: recovery supports training`;
        if (lower === "yellow") return `${clean}: use caution`;
        if (lower === "red") return `${clean}: recovery first`;
        return clean;
      }

      function rpeChip(value) {
        if (value == null) return "";
        return `RPE ${value}: ${rpePlain(value)}`;
      }

      function rpePlain(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "effort cap";
        if (number <= 4) return "easy";
        if (number <= 6) return "comfortable";
        if (number <= 7) return "hard but controlled";
        if (number <= 8) return "challenging";
        return "very hard";
      }

      function workoutTitle(activity, intensity) {
        const normalized = String(activity || "").trim().toLowerCase();
        if (!normalized || normalized === "general workout" || normalized === "workout plan") {
          if (String(intensity || "").includes("easy")) return "Recovery Workout";
          return "Useful Controlled Workout";
        }
        return titleCase(activity);
      }

      function workoutHeadline(data) {
        const intensity = titleCase(data.recommended_intensity || data.intensity || "guided");
        const cap = data.rpe_cap != null ? ` Keep it at RPE ${data.rpe_cap}/10, which means ${rpePlain(data.rpe_cap)}.` : "";
        if (String(data.recommended_intensity || data.intensity || "").includes("easy")) {
          return `Make this an easy session that leaves you feeling better.${cap}`;
        }
        if (String(data.recommended_intensity || data.intensity || "").includes("moderate")) {
          return `Do a useful ${intensity.toLowerCase()} session, not a prove-it workout.${cap}`;
        }
        return data.summary || data.recommendation || `Training looks available today.${cap}`;
      }

      function metricHint(label) {
        const lower = String(label || "").toLowerCase();
        if (lower.includes("rpe")) return "RPE = how hard it feels: 1 easy, 10 max.";
        if (lower.includes("intensity")) return "How aggressive the workout should feel.";
        if (lower.includes("hrv")) return "HRV = recovery stress signal compared with your usual.";
        if (lower === "heart rate") return "HR = current beats per minute.";
        if (lower.includes("resting") || lower.includes("rhr")) return "Resting HR = heart stress signal at rest.";
        if (lower.includes("load") || lower.includes("azm") || lower.includes("zone")) return "AZM = Fitbit hard-work minutes.";
        if (lower.includes("sleep")) return "Sleep is the biggest recovery input.";
        if (lower.includes("readiness")) return "Readiness blends sleep, heart, and load signals.";
        if (lower.includes("move")) return "Today's movement, not the whole week.";
        if (lower.includes("soreness")) return "Your check-in can override good wearable scores.";
        if (lower.includes("goal")) return "Goal pressure comes after recovery signals.";
        if (lower.includes("vitals")) return "Extra recovery context from Fitbit.";
        return "";
      }

      function explainEvidenceItem(item) {
        let text = String(item || "");
        if (text.includes("HRV") && !text.includes("recovery stress signal")) {
          text = text.replaceAll("HRV", "HRV (recovery stress signal)");
        }
        if (text.includes("RHR") && !text.includes("resting heart rate")) {
          text = text.replaceAll("RHR", "RHR (resting heart rate)");
        }
        if (/resting heart rate|Resting HR/i.test(text) && !text.includes("heart stress")) {
          text = text.replace(/Resting heart rate/i, "Resting HR (resting heart rate; heart stress at rest)");
        }
        if (/Active Zone Minutes/.test(text) && !text.includes("hard-work minutes")) {
          text = text.replaceAll("Active Zone Minutes", "Active Zone Minutes (Fitbit hard-work minutes)");
        }
        return text;
      }

      function explainPrescription(value) {
        const text = String(value || "");
        const match = text.match(/RPE\\s*<=\\s*(\\d+)/i);
        if (!match) return text;
        return `${text} (${rpePlain(match[1])})`;
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
    "health-overview": {
        "status": "ok",
        "overview_type": "health_overview",
        "window_days": 7,
        "date_range": {"start": "2026-06-27", "end": "2026-07-03"},
        "headline": "Red readiness at 38/100; 5.1h latest sleep; 72 zone minutes; 36.0 ms HRV.",
        "daily_brief": {
            "summary": "Make today recovery-first unless there is a strong non-negotiable reason to train hard. Main constraint: Latest sleep is short at 5.1h.",
            "training_bias": "recovery-first",
            "today_plan": [
                "Bias toward recovery, mobility, walking, and earlier sleep.",
                "Do not add another max-effort conditioning block today.",
                "Choose exercises that avoid sore areas unless warm-up pain stays under 3/10.",
                "Keep the plan aligned with your goal: Train four days per week.",
            ],
            "priority_signals": [
                {
                    "category": "readiness",
                    "label": "Readiness",
                    "detail": "Red at 38/100.",
                    "impact": "Use readiness as the starting point, then adjust for symptoms and goals.",
                    "status": "watchout",
                },
                {
                    "category": "sleep",
                    "label": "Sleep",
                    "detail": "5.1h, 2.2h below recent average.",
                    "impact": "Short sleep should cap intensity.",
                    "status": "watchout",
                },
                {
                    "category": "heart",
                    "label": "HRV",
                    "detail": "36.0 ms, 36% below recent average.",
                    "impact": "HRV helps explain recovery pressure.",
                    "status": "watchout",
                },
                {
                    "category": "activity",
                    "label": "Training load (AZM)",
                    "detail": "72 Active Zone Minutes on 2026-07-02.",
                    "impact": "AZM are Fitbit hard-work minutes; high recent load should reduce extra intensity.",
                    "status": "watchout",
                },
                {
                    "category": "goal",
                    "label": "Goal progress",
                    "detail": "1/4 workout sessions logged; 3 remaining.",
                    "impact": "Use the goal as pressure only after recovery signals.",
                    "status": "context",
                },
            ],
            "prompt_suggestions": [
                "I feel a little off today but still want to move. What should I do?",
                "Compare sleep, HRV, resting heart rate, and load.",
                "My body feels sore. Plan around that.",
            ],
            "context_gaps": [
                "Pain location is not logged; ask where soreness is before choosing loaded movements."
            ],
            "confidence": "high",
        },
        "readiness": {
            "score": 38,
            "label": "red",
            "recommendation": "Prioritize recovery, mobility, walking, and sleep.",
        },
        "today": {
            "steps": 1600,
            "active_zone_minutes": 0,
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 72},
            "sleep": {"asleep_hours": 5.1},
            "hrv_ms": 36,
            "resting_heart_rate": 67,
        },
        "sections": {
            "activity": {
                "status": "ok",
                "totals": {"steps": 41200, "active_zone_minutes": 72},
                "highest_load_day": {"date": "2026-07-02", "active_zone_minutes": 72},
            },
            "sleep": {
                "status": "ok",
                "latest_asleep_hours": 5.1,
                "latest_vs_average_hours": -2.2,
                "days_with_sleep": 7,
            },
            "heart": {
                "status": "ok",
                "latest_hrv_ms": 36,
                "average_hrv_ms": 56.5,
                "latest_resting_heart_rate": 67,
                "average_resting_heart_rate": 57.5,
            },
            "recovery": {"status": "ok", "latest_spo2": 98.1},
            "workouts": {"status": "ok", "workout_count": 1},
        },
        "positives": ["Enough synced data is present to produce a personalized overview."],
        "watchouts": [
            "Latest sleep is short at 5.1h.",
            "HRV is running below the recent average.",
            "Recent training load is high: 72 zone minutes on 2026-07-02.",
        ],
        "next_actions": [
            "Bias toward recovery, mobility, walking, and earlier sleep.",
            "Do not add another max-effort conditioning block today.",
        ],
        "data_used": {"synced_metric_count": 9},
        "data_freshness": {"freshness_level": "fresh", "latest_observed_date": "2026-07-03"},
    },
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
        "coach_response": {
            "short_answer": "Make today recovery-biased: useful movement is fine, but do not chase fitness today.",
            "what_to_do": [
                "Make today recovery-biased: walk, mobility, easy cardio, or rest.",
                "Keep RPE (how hard it feels) at or below 6/10, which means comfortable.",
                "You are 2 session(s) from the weekly target, but recovery signals make an easy day smarter.",
                "Protect sleep tonight and reassess after the next sync.",
            ],
            "why": [
                "HRV (recovery stress signal) is below recent baseline: 36.0 ms vs 56.5 ms. Lower HRV than usual is a caution signal, so cap intensity.",
                "Resting HR (resting heart rate; heart stress at rest) is elevated: 67 bpm vs 58 bpm baseline. Elevated versus your usual can point to stress, illness, fatigue, or under-recovery.",
                "Latest training load: 72 Active Zone Minutes (AZM, Fitbit hard-work minutes) on 2026-07-02.",
                "Latest soreness check-in is 7/10. Your own body report can override a good wearable score.",
            ],
            "avoid": ["Loading sore areas aggressively", "Another hard conditioning block today"],
        },
        "data_freshness": {"freshness_level": "fresh", "latest_observed_date": "2026-07-03"},
    },
    "workout-plan": {
        "status": "ok",
        "planned_activity": "chest and back gym session",
        "planned_date": "today",
        "target_areas": ["chest", "back"],
        "constraints": "lower back soreness after squash",
        "summary": "For today, keep chest and back at easy intensity (recovery pace) with an RPE cap around 6/10 (comfortable, should not feel like a grind). Treat this as a quality/recovery-biased session because recovery signals are red.",
        "recommended_intensity": "easy",
        "rpe_cap": 6,
        "readiness": {
            "score": 44,
            "label": "red",
            "evidence": [
                "HRV is below recent baseline: 31.3 ms vs 60.9 ms.",
                "Resting heart rate is slightly elevated: 65 bpm.",
                "Recent training load is high: 63 zone minutes on 2026-07-02.",
            ],
        },
        "focus": [
            "Prefer chest-supported rows, pulldowns, and cable work.",
            "A productive session today means leaving the gym feeling better, not crushed.",
        ],
        "warmup": [
            "5-8 minutes easy cardio to check readiness.",
            "Dynamic hips, thoracic rotations, and shoulder/scapular activation.",
        ],
        "exercise_blocks": [
            {
                "exercise": "Machine chest press",
                "sets": "2-3",
                "reps": "8-10",
                "intensity": "RPE <= 6",
                "note": "Stable torso; leave 3-4 reps in reserve if recovery is red.",
                "alternative": "Flat dumbbell press with a neutral, pain-free arch.",
            },
            {
                "exercise": "Chest-supported row",
                "sets": "2-3",
                "reps": "10-12",
                "intensity": "RPE <= 6",
                "note": "Keep the lower back quiet; squeeze without yanking.",
                "alternative": "Seated cable row with chest support.",
            },
            {
                "exercise": "Neutral-grip lat pulldown",
                "sets": "3",
                "reps": "10-12",
                "intensity": "RPE <= 6",
                "note": "Stay tall and avoid leaning far back.",
                "alternative": "Assisted pull-up if smooth and controlled.",
            },
        ],
        "session_guidance": [
            "Do not chase PRs; keep every compound lift 3-4 reps in reserve.",
            "Keep working sets at or below RPE 6/10 (comfortable, should not feel like a grind).",
            "Keep the session near 60 minutes including warm-up.",
        ],
        "avoid": ["Heavy deadlifts", "Heavy bent-over rows", "Aggressive bench arch if low back feels sensitive"],
        "substitutions": [
            "Bent-over row -> chest-supported row.",
            "Standing cable row -> seated cable row with chest support.",
            "Barbell bench with a big arch -> machine or dumbbell press.",
        ],
        "limiting_factors": [
            "HRV is below recent baseline: 31.3 ms vs 60.9 ms.",
            "Resting heart rate is slightly elevated: 65 bpm.",
            "User-stated lower-back or hip constraint should cap spinal loading.",
        ],
        "data_used": {
            "readiness_score": 44,
            "readiness_label": "red",
            "sleep_asleep_hours": 6.1,
            "sleep_sessions": 2,
            "hrv_ms": 31.3,
            "resting_heart_rate": 65,
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 63},
        },
        "coach_response": {
            "short_answer": "For chest and back gym session, make the win leaving better than you started.",
            "what_to_do": [
                "For today, keep chest and back at easy intensity with an RPE cap around 6/10.",
                "RPE (how hard it feels) cap: 6/10, which means comfortable.",
                "Do not chase PRs; keep every compound lift 3-4 reps in reserve.",
                "Prefer chest-supported rows, pulldowns, and cable work.",
            ],
            "why": [
                "HRV (recovery stress signal) is below recent baseline: 31.3 ms vs 60.9 ms. Lower HRV than usual is a caution signal, so cap intensity.",
                "Resting HR (resting heart rate; heart stress at rest) is slightly elevated: 65 bpm.",
                "User-stated lower-back or hip constraint should cap spinal loading.",
            ],
            "avoid": ["Heavy deadlifts", "Heavy bent-over rows", "Aggressive bench arch if low back feels sensitive"],
        },
    },
    "active-workout": {
        "status": "ok",
        "guidance_type": "active_workout_guidance",
        "planned_activity": "Intervals",
        "decision": "stop_and_assess",
        "headline": "Stop the hard work now and treat this as a safety check, not a training decision.",
        "immediate_actions": [
            "Stop the set or interval now and move to a safe seated or standing position.",
            "Do not resume hard training while these symptoms are present.",
            "Seek urgent medical care for chest pain, fainting, severe shortness of breath, or symptoms that are new, severe, or worsening.",
        ],
        "modifications": ["If symptoms fully resolve and are mild, switch only to an easy cooldown or end the session."],
        "avoid": ["Continuing intervals or heavy sets", "Trying to push through symptoms"],
        "safety_flags": [
            "Reported symptoms may need medical caution; stop hard training and seek urgent care for chest pain, fainting, severe shortness of breath, or new/worsening symptoms."
        ],
        "evidence": [
            "Live heart rate reported: 178 bpm.",
            "Live effort reported: RPE 9/10.",
            "Live pain reported: 2/10.",
        ],
        "readiness": {"score": 62, "label": "yellow"},
        "live_inputs": {
            "current_heart_rate_bpm": 178,
            "current_rpe": 9,
            "pain_level": 2,
            "symptoms": "dizzy during the interval",
            "elapsed_minutes": 18,
            "planned_duration_minutes": 35,
        },
        "data_used": {
            "readiness_score": 62,
            "readiness_label": "yellow",
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 35},
        },
        "coach_response": {
            "short_answer": "Stop the hard part now. Treat this as a safety decision, not a toughness decision.",
            "what_to_do": [
                "Stop the set or interval now and move to a safe seated or standing position.",
                "Do not resume hard training while these symptoms are present.",
                "Seek urgent medical care for chest pain, fainting, severe shortness of breath, or symptoms that are new, severe, or worsening.",
            ],
            "live_context": [
                "HR (heart rate right now): 178 bpm.",
                "RPE (how hard it feels): 9/10, which means very hard.",
                "Pain: 2/10. Keep it 3/10 or lower, or stop that movement.",
            ],
            "why": [
                "Reported symptoms may need medical caution; stop hard training and seek urgent care for chest pain, fainting, severe shortness of breath, or new/worsening symptoms.",
            ],
            "stop_if": [
                "Stop if symptoms are new, severe, or worsening.",
                "Stop if heart rate or breathing does not settle after 3-5 easy minutes.",
                "Stop if pain rises above 3/10 or changes your form.",
            ],
        },
        "safety_note": "This is in-session fitness guidance, not medical diagnosis or emergency care.",
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
