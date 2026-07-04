from __future__ import annotations

import json


WIDGET_URI = "ui://mehair/today-v31.html"
LEGACY_WIDGET_URIS = (
    "ui://mehair/today-v1.html",
    "ui://mehair/today-v2.html",
    "ui://mehair/today-v3.html",
    "ui://mehair/today-v4.html",
    "ui://mehair/today-v5.html",
    "ui://mehair/today-v6.html",
    "ui://mehair/today-v7.html",
    "ui://mehair/today-v8.html",
    "ui://mehair/today-v9.html",
    "ui://mehair/today-v10.html",
    "ui://mehair/today-v11.html",
    "ui://mehair/today-v12.html",
    "ui://mehair/today-v13.html",
    "ui://mehair/today-v14.html",
    "ui://mehair/today-v15.html",
    "ui://mehair/today-v16.html",
    "ui://mehair/today-v17.html",
    "ui://mehair/today-v18.html",
    "ui://mehair/today-v19.html",
    "ui://mehair/today-v20.html",
    "ui://mehair/today-v21.html",
    "ui://mehair/today-v22.html",
    "ui://mehair/today-v23.html",
    "ui://mehair/today-v24.html",
    "ui://mehair/today-v25.html",
    "ui://mehair/today-v26.html",
    "ui://mehair/today-v27.html",
    "ui://mehair/today-v28.html",
    "ui://mehair/today-v29.html",
    "ui://mehair/today-v30.html",
)
WIDGET_RESOURCE_URIS = (WIDGET_URI, *LEGACY_WIDGET_URIS)
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"


TODAY_WIDGET_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>mehair coach</title>
    <style>
      :root {
        color-scheme: light;
        --brand: #d63384;
        --brand-soft: #fff0f7;
        --brand-ink: #81164d;
        --state: #d63384;
        --state-soft: #fff0f7;
        --ink: #171a1f;
        --muted: #667078;
        --line: #f1d5e3;
        --surface: #ffffff;
        --wash: #fff8fc;
        --tile: #fffafd;
        --accent: #d63384;
        --accent-soft: #fff0f7;
        --band-color: #d63384;
        --band-soft: #fff0f7;
        --warn: #9b741c;
        --danger: #a94f43;
        --ok: #2f7a5f;
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
        --accent: var(--brand);
        --accent-soft: var(--brand-soft);
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 8px 28px rgba(214, 51, 132, 0.08);
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
        border-bottom: 1px solid #f7deea;
        background: #fffafd;
      }

      .identity {
        min-width: 0;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: var(--brand);
        font-size: 11px;
        font-weight: 820;
        letter-spacing: 0;
        text-transform: none;
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

      .data-window {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        gap: 8px 10px;
        align-items: center;
        border-top: 1px solid #f7deea;
        border-bottom: 1px solid #f7deea;
        background: linear-gradient(90deg, #fff0f7, #fffafd);
        padding: 9px 14px;
      }

      .data-window b {
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        border: 1px solid #f0a9c9;
        border-radius: 999px;
        background: #fff;
        color: var(--brand-ink);
        font-size: 11px;
        font-weight: 840;
        line-height: 1.1;
        padding: 5px 8px;
      }

      .data-window b::before {
        content: "";
        flex: 0 0 auto;
        width: 7px;
        height: 7px;
        margin-right: 6px;
        border-radius: 999px;
        background: var(--sync-dot, var(--brand));
        box-shadow: 0 0 0 2px var(--sync-soft, var(--brand-soft));
      }

      .data-window span {
        min-width: 0;
        color: #444d55;
        font-size: 12px;
        font-weight: 680;
        line-height: 1.3;
      }

      .chip {
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        max-width: 100%;
        border: 1px solid #f1d5e3;
        border-radius: 999px;
        background: #fffafd;
        color: #313940;
        font-size: 12px;
        font-weight: 720;
        line-height: 1.15;
        padding: 5px 9px;
      }

      .chip.accent {
        border-color: #f0a9c9;
        background: var(--brand-soft);
        color: var(--brand-ink);
      }

      .hero {
        display: grid;
        grid-template-columns: minmax(128px, 150px) 1fr;
        gap: 12px;
        padding: 14px;
      }

      .hero.no-score {
        grid-template-columns: 1fr;
      }

      .score-card {
        display: grid;
        justify-items: center;
        align-content: start;
        gap: 8px;
        min-width: 0;
      }

      .gauge {
        position: relative;
        display: grid;
        place-items: center;
        width: min(150px, 100%);
        aspect-ratio: 1;
        min-height: 128px;
        border: 1px solid #f0d5e1;
        border-radius: 50%;
        background: conic-gradient(var(--brand) calc(var(--score, 0) * 1%), #f8dce9 0);
        overflow: hidden;
      }

      .gauge-inner {
        display: grid;
        gap: 2px;
        place-items: center;
        width: 92px;
        height: 92px;
        border: 1px solid #f0d5e1;
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

      .score-note {
        margin: 0;
        color: #58626a;
        font-size: 11px;
        font-weight: 650;
        line-height: 1.3;
        text-align: center;
      }

      .score-state {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        min-height: 23px;
        border: 1px solid #f0a9c9;
        border-radius: 999px;
        background: var(--brand-soft);
        color: var(--brand-ink);
        font-size: 11px;
        font-weight: 820;
        line-height: 1.1;
        padding: 4px 8px;
        text-align: center;
      }

      .score-state::before {
        content: "";
        flex: 0 0 auto;
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: var(--band-color);
        box-shadow: 0 0 0 2px var(--band-soft);
      }

      .band-legend {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 3px;
        width: 100%;
        color: #667078;
        font-size: 9px;
        font-weight: 760;
        line-height: 1.15;
        text-align: center;
      }

      .band-legend span {
        --dot: var(--brand);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        border: 1px solid #f0d5e1;
        border-radius: 999px;
        background: #fffafd;
        padding: 4px 3px;
      }

      .band-legend span::before {
        content: "";
        flex: 0 0 auto;
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: var(--dot);
      }

      .band-legend .band-green { --dot: var(--ok); }
      .band-legend .band-yellow { --dot: var(--warn); }
      .band-legend .band-red { --dot: var(--danger); }

      .plan-box {
        display: grid;
        gap: 10px;
        align-content: start;
        min-width: 0;
        border: 1px solid #f0cfe0;
        border-left: 4px solid var(--brand);
        border-radius: 8px;
        background: #fffafd;
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

      .dose-cue {
        display: flex;
        align-items: flex-start;
        gap: 7px;
        border: 1px solid #f0a9c9;
        border-radius: 8px;
        background: #fff0f7;
        color: var(--brand-ink);
        padding: 7px 8px;
        font-size: 12px;
        font-weight: 760;
        line-height: 1.3;
      }

      .dose-cue::before {
        content: "";
        flex: 0 0 auto;
        width: 8px;
        height: 8px;
        margin-top: 4px;
        border-radius: 999px;
        background: var(--brand);
        box-shadow: 0 0 0 2px #fff;
      }

      .focus-list {
        display: grid;
        gap: 6px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .focus-list li {
        border-left: 3px solid var(--brand);
        border-radius: 0 6px 6px 0;
        background: #fff5fa;
        padding: 7px 8px;
        color: #303942;
        font-size: 12px;
        line-height: 1.34;
      }

      .workout-blocks {
        display: grid;
        gap: 8px;
        border-top: 1px solid #f7deea;
        padding: 0 14px 14px;
      }

      .workout-block {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 5px 10px;
        align-items: start;
        border: 1px solid #f0d5e1;
        border-radius: 8px;
        background: #fffafd;
        padding: 10px;
      }

      .workout-block b {
        min-width: 0;
        color: #20272e;
        font-size: 13px;
        font-weight: 820;
        line-height: 1.2;
      }

      .workout-prescription {
        grid-column: 1 / -1;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        min-width: 0;
      }

      .rx-pill {
        display: inline-grid;
        grid-template-columns: auto minmax(0, 1fr);
        gap: 4px;
        align-items: baseline;
        max-width: 100%;
        border: 1px solid #f0d5e1;
        border-radius: 999px;
        background: #fff5fa;
        padding: 5px 8px;
      }

      .rx-pill b {
        color: var(--brand-ink);
        font-size: 10px;
        font-weight: 840;
        line-height: 1.2;
        text-transform: uppercase;
      }

      .rx-pill span {
        min-width: 0;
        overflow-wrap: anywhere;
        color: var(--brand);
        font-size: 12px;
        font-weight: 780;
        line-height: 1.2;
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
        border: 1px solid #f0d5e1;
        border-top: 3px solid #f2b2cf;
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

      .label-key {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        border-top: 1px solid #f7deea;
        padding: 0 14px 14px;
      }

      .label-heading {
        grid-column: 1 / -1;
        color: var(--brand);
        font-size: 11px;
        font-weight: 820;
        line-height: 1.2;
        text-transform: uppercase;
      }

      .label-pill {
        min-width: 0;
        border: 1px solid #f0d5e1;
        border-left: 3px solid var(--brand);
        border-radius: 8px;
        background: #fffafd;
        padding: 9px 10px;
      }

      .label-pill b {
        display: block;
        color: var(--ink);
        font-size: 12px;
        font-weight: 820;
        line-height: 1.2;
      }

      .label-pill span {
        display: block;
        margin-top: 3px;
        color: #59636b;
        font-size: 11px;
        line-height: 1.3;
      }

      .signal-heading {
        border-top: 1px solid #f7deea;
        padding: 12px 14px 7px;
        color: var(--brand);
        font-size: 11px;
        font-weight: 820;
        line-height: 1.2;
        text-transform: uppercase;
      }

      .signal-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }

      .signal-card {
        min-width: 0;
        border: 1px solid #f0d5e1;
        border-left: 3px solid var(--brand);
        border-radius: 8px;
        background: #fffafd;
        padding: 9px 10px;
      }

      .signal-card b {
        display: block;
        overflow-wrap: anywhere;
        color: #20272e;
        font-size: 12px;
        font-weight: 820;
        line-height: 1.2;
      }

      .signal-card span,
      .signal-card small {
        display: block;
        margin-top: 3px;
        color: #59636b;
        font-size: 11px;
        line-height: 1.3;
      }

      .signal-card span {
        color: var(--brand-ink);
        font-weight: 760;
      }

      .details {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        border-top: 1px solid #f7deea;
        background: #fffafd;
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
        background: var(--brand);
        vertical-align: 1px;
      }

      @media (max-width: 560px) {
        body { padding: 8px; }
        .mast { grid-template-columns: 1fr; gap: 8px; }
        .stamp { min-width: 0; text-align: left; }
        .data-window { grid-template-columns: 1fr; }
        .hero { grid-template-columns: 1fr; }
        .score-card { justify-self: center; }
        .gauge { justify-self: center; min-height: 136px; }
        .workout-block { grid-template-columns: 1fr; }
        .workout-block span { white-space: normal; }
        .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .signal-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .details { grid-template-columns: 1fr; }
      }

      @media (max-width: 430px) {
        .metrics { grid-template-columns: 1fr; }
        .label-key { grid-template-columns: 1fr; }
        .signal-strip { grid-template-columns: 1fr; }
      }

      @media (max-width: 340px) {
        .metrics { grid-template-columns: 1fr; }
        .label-key { grid-template-columns: 1fr; }
        .signal-strip { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="panel" id="root">
        <div class="empty">
          <strong>mehair coach</strong>
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
        const data =
          response?.structuredContent ||
          response?.result?.structuredContent ||
          response?.toolOutput ||
          response;
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

      window.addEventListener(
        "openai:set_globals",
        (event) => {
          const globals = event.detail?.globals || {};
          updateFromResponse(globals.toolOutput || window.openai?.toolOutput);
        },
        { passive: true }
      );

      async function initialize() {
        updateFromResponse(window.openai?.toolOutput);
        try {
          await rpcRequest("ui/initialize", {
            appInfo: { name: "mehair coach", version: "0.8.0" },
            appCapabilities: {},
            protocolVersion: "2026-01-26",
          });
          rpcNotify("ui/notifications/initialized", {});
          updateFromResponse(window.openai?.toolOutput);
        } catch (error) {
          console.error(error);
          updateFromResponse(window.openai?.toolOutput);
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
        renderModel(withDataWindow(toViewModel(data), data));
      }

      function renderEmpty(message, status) {
        root.style.setProperty("--accent", "#d63384");
        root.style.setProperty("--accent-soft", "#fff0f7");
        root.style.setProperty("--state", "#d63384");
        root.style.setProperty("--state-soft", "#fff0f7");
        root.style.setProperty("--band-color", "#d63384");
        root.style.setProperty("--band-soft", "#fff0f7");
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
          data.requested_metrics ||
          data.suggested_card
        );
      }

      function toViewModel(data) {
        if (data?.suggested_card && typeof data.suggested_card === "object") return toViewModel(data.suggested_card);
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
        const score = finiteNumber(readiness.score, 0);
        const band = readinessBand(score, label);
        const brief = data.daily_brief || {};
        const sections = data.sections || {};
        const activity = sections.activity || {};
        const sleep = sections.sleep || {};
        const heart = sections.heart || {};
        const recovery = sections.recovery || {};
        const workouts = sections.workouts || {};
        const dataUsed = data.data_used || {};
        const freshness = data.data_freshness || {};
        const signalSnapshot = data.available_signal_snapshot || {};
        const signalById = Object.fromEntries((signalSnapshot.signals || []).map((item) => [item.id, item]));
        const dateRange = data.date_range || {};
        const range = dateRange.start && dateRange.end ? `${dateRange.start} to ${dateRange.end}` : "";
        const windowDays = finiteNumber(data.window_days, 0) || dateRangeDays(dateRange.start, dateRange.end);
        const rangeLabel = compactRangeLabel(dateRange, windowDays);
        const today = data.today || {};
        const latestActivity = activity.latest || {};
        const latestLoad = today.latest_training_load || activity.highest_load_day || {};
        const sleepHours = sleep.latest_asleep_hours ?? data.today?.sleep?.asleep_hours ?? data.today?.sleep?.duration_hours;
        const hrv = heart.latest_hrv_ms ?? data.today?.hrv_ms;
        const rhr = heart.latest_resting_heart_rate ?? data.today?.resting_heart_rate;
        const todaySteps = today.steps ?? latestActivity.steps;
        const windowSteps = activity.totals?.steps;
        const latestLoadAzm = latestLoad.active_zone_minutes ?? today.active_zone_minutes ?? latestActivity.active_zone_minutes;
        const windowAzm = activity.totals?.active_zone_minutes;
        const latestLoadDetail = latestLoad.date
          ? [ `latest ${latestLoad.date}`, windowAzm != null && rangeLabel ? `${intText(windowAzm)} AZM over ${rangeLabel}` : "" ].filter(Boolean).join("; ")
          : (rangeLabel ? `${rangeLabel} total` : "latest");
        const stepAverage = activity.averages?.steps_per_day;
        const stepCoverage = activity.coverage || {};
        const stepSummary = activity.step_window_summary || {};
        const stepAverageLabel = stepSummary.average_display || (stepAverage != null ? `${intText(stepAverage)}/day avg on recorded step days` : "");
        const stepRecordedLabel = stepCoverage.days_with_steps != null && stepCoverage.days_in_lookback != null
          ? `${stepCoverage.days_with_steps}/${stepCoverage.days_in_lookback} days with steps`
          : rangeLabel;
        const moveMetric = todaySteps != null
          ? [
              "Steps",
              `${intText(todaySteps)} steps`,
              [ "today so far", stepAverageLabel, stepRecordedLabel ].filter(Boolean).join("; "),
              "Movement load context; mostly useful for leg fatigue and total day load.",
            ]
          : [
              "Steps window",
              windowSteps != null ? `${intText(windowSteps)} steps` : null,
              [stepSummary.display || rangeLabel, stepAverageLabel].filter(Boolean).join("; "),
              "Movement load context; mostly useful for leg fatigue and total day load.",
            ];
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
        const breathingSignal = signalById.spo2 || signalById.respiratory_rate || signalById.sleep_temperature;
        const capacitySignal = signalById.vo2_max;
        const checkedSignals = prioritySignalStrip(signalSnapshot.signals || []);
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
          accent: readinessAccent(band),
          stateLabel: band,
          title: "Health Overview",
          eyebrow: "mehair coach",
          date: range || data.data_freshness?.latest_observed_date || "",
          chips: [
            readinessChip(label, score),
            brief.training_bias ? titleCase(brief.training_bias) : "",
            `${dataUsed.synced_metric_count || 0} metrics`,
            freshnessChip(freshness),
          ].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: brief.summary || data.headline || readiness.recommendation || "All synced health data summarized.",
          focusTitle: "Today Plan",
          focus: primaryActions,
          labels: defaultLabelKey(["Readiness", "HRV", "Resting HR", "AZM", "SpO2", "Respiratory rate"]),
          metrics: [
            moveMetric,
            ["Training Load", latestLoadAzm != null ? `${intText(latestLoadAzm)} AZM` : null, latestLoadDetail, "AZM = Fitbit hard-work minutes."],
            ["Sleep vs usual", sleepDelta != null ? `${signed(sleepDelta)}h` : (sleepHours != null ? `${num(sleepHours, 1)}h` : null), sleepHours != null ? `latest ${num(sleepHours, 1)}h` : ""],
            ["HRV vs usual", hrvDelta != null ? `${signed(hrvDelta)}%` : (hrv != null ? `${num(hrv, 1)} ms` : null), hrv != null && heart.average_hrv_ms ? `${num(hrv, 1)} now; usual ${num(heart.average_hrv_ms, 1)} ms` : "", "HRV = recovery stress signal."],
            ["Resting HR vs usual", rhrDelta != null ? `${signed(rhrDelta)} bpm` : (rhr != null ? `${num(rhr, 1)} bpm` : null), rhr != null && heart.average_resting_heart_rate ? `${num(rhr, 0)} now; usual ${num(heart.average_resting_heart_rate, 0)} bpm` : "", "Resting HR = resting heart rate."],
            breathingSignal
              ? signalMetric(breathingSignal, rangeLabel)
              : null,
            capacitySignal
              ? signalMetric(capacitySignal, rangeLabel)
              : null,
            workouts.workout_count > 0
              ? ["Workouts", intText(workouts.workout_count), rangeLabel || range || "synced window"]
              : vitalsValue
                ? ["Vitals", vitalsValue, vitalsDetail]
                : ["Freshness", titleCase(freshness.freshness_level || "unknown"), freshness.latest_observed_date ? `latest ${freshness.latest_observed_date}` : ""],
          ].filter(Boolean),
          signalStrip: checkedSignals,
          evidenceTitle: prioritySignals.length ? "Priority Signals" : "Positives",
          evidence: prioritySignals.length ? prioritySignals : data.positives || [],
          secondaryTitle: contextGaps.length ? "Watchouts & Gaps" : "Watchouts",
          secondary: watchoutsAndGaps,
        };
      }

      function questionCluesModel(data) {
        const readiness = data.readiness || {};
        const score = finiteNumber(readiness.score, 0);
        const band = readinessBand(score, readiness.label || "pending");
        const metrics = data.relevant_metrics || [];
        const available = metrics.filter((item) => Number(item.records || 0) > 0);
        const intents = data.intent_hints || [];
        const freshness = data.data_freshness || {};
        const signalSnapshot = data.available_signal_snapshot || {};
        const snapshotSignals = prioritySignalStrip(signalSnapshot.signals || []);
        const topMetrics = (available.length ? available : metrics).slice(0, 6);
        const hasSafetyFlags = (data.safety_flags || []).length > 0;
        return {
          accent: hasSafetyFlags ? "#a94f43" : "#d63384",
          stateLabel: band,
          title: hasSafetyFlags ? "Health Check" : "Signals That Matter",
          eyebrow: "mehair coach",
          date: data.today?.activity_date && data.today?.recovery_date && data.today.activity_date !== data.today.recovery_date
            ? `Activity ${data.today.activity_date}; recovery ${data.today.recovery_date}`
            : data.today?.activity_date || freshness.latest_observed_date || "",
          chips: [
            titleCase(intents[0] || "overview"),
            `${available.length}/${metrics.length || 0} metrics`,
            freshnessChip(freshness),
          ].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          showScore: !hasSafetyFlags,
          headline: data.headline || "Useful Fitbit signals selected for this question.",
          focusTitle: hasSafetyFlags ? "Safety First" : "Why I Checked These",
          focus: hasSafetyFlags ? data.safety_flags || [] : data.clues || [],
          metrics: snapshotSignals.length
            ? snapshotSignals.map((item) => signalMetric(item, "latest synced"))
            : topMetrics.map((item) => [
                item.label || item.id,
                intText(item.records ?? 0),
                item.latest_observed_date || "not synced",
              ]),
          evidenceTitle: hasSafetyFlags ? "Relevant Metrics" : "Why These",
          evidence: snapshotSignals.length
            ? snapshotSignals.map((item) => `${item.label || item.id}: ${item.coaching_use || item.why_it_matters || "Useful context."}`)
            : topMetrics.map((item) => `${item.label || item.id}: ${item.reason || "Useful context."}`),
          secondaryTitle: hasSafetyFlags ? "Data Clues" : "Watchouts",
          secondary: hasSafetyFlags ? data.clues || [] : data.watchouts || [],
          signalStrip: snapshotSignals,
        };
      }

      function recoveryComparisonModel(data) {
        const readiness = data.readiness || {};
        const latest = data.latest || {};
        const baseline = data.baseline || {};
        const deltas = data.current_vs_baseline || {};
        const label = readiness.label || "pending";
        const score = finiteNumber(readiness.score, 0);
        const band = readinessBand(score, label);
        const sleepTemp = latest.sleep_temperature || {};
        const signalSnapshot = data.available_signal_snapshot || {};
        return {
          accent: readinessAccent(band),
          stateLabel: band,
          title: "Recovery Signals",
          eyebrow: "mehair coach",
          date: data.date_range?.start && data.date_range?.end ? `${data.date_range.start} to ${data.date_range.end}` : latest.date || "",
          chips: [
            readinessChip(label, score),
            `${data.data_used?.days_compared || data.window_days || 14} days`,
            freshnessChip(data.data_freshness || {}),
          ].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: data.headline || "Sleep, heart, and load compared against baseline.",
          focusTitle: "What This Means For Training",
          focus: data.insights || [],
          metrics: [
            ["Sleep", latest.sleep_hours != null ? `${num(latest.sleep_hours, 1)}h` : null, baseline.sleep_hours != null ? `usual ${num(baseline.sleep_hours, 1)}h` : ""],
            ["Sleep change", deltas.sleep_hours_delta != null ? `${signed(deltas.sleep_hours_delta)}h` : null],
            ["HRV", latest.hrv_ms != null ? `${num(latest.hrv_ms, 1)} ms` : null, baseline.hrv_ms != null ? `usual ${num(baseline.hrv_ms, 1)}` : ""],
            ["HRV change", deltas.hrv_percent_delta != null ? `${signed(deltas.hrv_percent_delta)}%` : null],
            ["Resting HR", latest.resting_heart_rate != null ? `${latest.resting_heart_rate} bpm` : null, baseline.resting_heart_rate != null ? `usual ${num(baseline.resting_heart_rate, 1)}` : ""],
            ["Load", latest.active_zone_minutes != null ? `${latest.active_zone_minutes} AZM` : null, baseline.active_zone_minutes != null ? `usual ${num(baseline.active_zone_minutes, 1)}` : ""],
            ["Respiratory rate", latest.respiratory_rate != null ? `${num(latest.respiratory_rate, 1)}` : null, baseline.respiratory_rate != null ? `usual ${num(baseline.respiratory_rate, 1)}` : "", "Breathing rate context."],
            ["SpO2", latest.spo2_avg != null ? `${num(latest.spo2_avg, 1)}%` : null, baseline.spo2_avg != null ? `usual ${num(baseline.spo2_avg, 1)}%` : "", "Oxygen context, not a standalone go signal."],
            ["Sleep temperature", sleepTemp.delta_celsius != null ? `${signed(sleepTemp.delta_celsius)} C` : null, "change from usual", "Temperature deviation is a secondary clue."],
          ].filter((item) => item[1] != null),
          evidenceTitle: "Positives",
          evidence: data.positives || [],
          secondaryTitle: "Watchouts",
          secondary: data.watchouts || [],
          signalStrip: prioritySignalStrip(signalSnapshot.signals || []),
        };
      }

      function todayWorkoutModel(data) {
        const readiness = data.readiness || {};
        const label = readiness.label || data.data_used?.readiness_label || "pending";
        const score = finiteNumber(readiness.score, 0);
        const band = readinessBand(score, label);
        const today = data.today || {};
        const sleep = today.sleep || {};
        const goal = data.goal_context || {};
        const subjective = data.subjective_context || {};
        const dataUsed = data.data_used || {};
        const freshness = data.data_freshness || {};
        const coach = data.coach_response || {};
        const signalSnapshot = data.available_signal_snapshot || {};
        const sleepHours = dataUsed.latest_sleep_hours ?? sleep.asleep_hours ?? sleep.duration_hours;
        const deadlineMinutes = firstFinite(dataUsed.deadline_movement_minutes, subjective.deadline_movement_minutes);
        const reserveEnergy = Boolean(dataUsed.reserve_energy_obligation || subjective.reserve_energy_obligation || deadlineMinutes != null);
        const goalDetail = goal.remaining_sessions != null
          ? `${goal.remaining_sessions} goal sessions left`
          : goal.target || "";
        const activityWindow = data.activity_date || dataUsed.activity_date || data.latest_date || "today";
        const activityWindowLabel = activityWindow === "today" ? "today so far" : `${activityWindow} so far`;
        const stepsValue = today.steps ?? dataUsed.steps_today;
        const azmValue = today.active_zone_minutes ?? dataUsed.active_zone_minutes_today;
        return {
          accent: readinessAccent(band),
          stateLabel: band,
          title: todayWorkoutTitle(data, reserveEnergy, deadlineMinutes),
          eyebrow: "mehair coach",
          date: data.activity_date && data.recovery_date && data.activity_date !== data.recovery_date
            ? `Activity ${data.activity_date}; recovery ${data.recovery_date}`
            : data.activity_date || data.latest_date || "",
          chips: [
            intensityChip(data.intensity),
            rpeChip(data.rpe_cap),
            readinessChip(label, score),
            freshnessChip(freshness),
          ].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: coach.short_answer || workoutHeadline(data),
          focusTitle: reserveEnergy ? "Minimum Dose" : coach.session_blueprint ? "Next Session" : "What To Do",
          focus: coach.session_blueprint || coach.what_to_do || data.next_actions || [],
          labels: coach.labels_explained || defaultLabelKey(["Readiness", "RPE", "HRV", "Resting HR", "AZM"]),
          metrics: [
            ["Steps", stepsValue != null ? `${intText(stepsValue)} steps` : null, activityWindowLabel, "Movement load in this window; mostly useful for leg fatigue."],
            ["AZM", azmValue != null ? `${intText(azmValue)} min` : null, activityWindowLabel, "AZM = Fitbit hard-work minutes in this window."],
            ["Sleep", sleepHours != null ? `${num(sleepHours, 1)}h` : null],
            ["HRV", dataUsed.hrv_ms != null ? `${num(dataUsed.hrv_ms, 1)} ms` : null],
            ["Soreness", subjective.soreness != null ? `${subjective.soreness}/10` : null, subjective.energy != null ? `energy ${subjective.energy}/10` : ""],
            ["Goal", goal.remaining_sessions != null ? intText(goal.remaining_sessions) : "No goal", goalDetail],
          ],
          signalStrip: prioritySignalStrip(signalSnapshot.signals || []),
          evidenceTitle: "What This Means",
          evidence: [coach.data_story, ...(coach.why || prioritizeWorkoutEvidence(data.evidence || data.why || []))].filter(Boolean),
          secondaryTitle: coach.stop_if ? "Stop If" : "Avoid",
          secondary: coach.stop_if || coach.avoid || data.avoid || [],
        };
      }

      function todayWorkoutTitle(data, reserveEnergy, deadlineMinutes) {
        if (reserveEnergy || deadlineMinutes != null) {
          const text = String(data.subjective_context?.current_feeling || data.data_used?.current_feeling || "").toLowerCase();
          const has = (pattern) => pattern.test(text);
          if (has(/\\b(class|school|lecture)\\b/)) return "Before Class Movement";
          if (has(/\\bdinner\\b/)) return "Before Dinner Movement";
          if (has(/\\b(date|reservation|plans?|event|party)\\b/)) return "Before Plans Movement";
          if (has(/\\b(travel|flight|commute|drive)\\b/)) return "Before Travel Movement";
          if (
            has(/\\b(meeting|call|appointment|presentation|interview|office|shift)\\b/) ||
            has(/\\bbefore\\s+(work|my\\s+shift|shift)\\b/) ||
            has(/\\b(work|shift)\\s+(in|within|starts|begins)\\b/)
          ) return "Before Work Movement";
          if (
            has(/\\b(later today|tonight|this evening)\\b/) &&
            has(/\\b(pickleball|tennis|squash|basketball|soccer|hike|walk|run|race|match|game)\\b/)
          ) return "Game-Day Primer";
          if (
            has(/\\b(tomorrow|upcoming)\\b/) &&
            has(/\\b(pickleball|tennis|squash|basketball|soccer|hike|walk|run|race|match|game)\\b/)
          ) return "Tomorrow-Friendly Workout";
          return "Minimum Useful Movement";
        }
        if (String(data.intensity || "").includes("easy")) return "Recovery Workout";
        return "Today's Workout";
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
        const band = readinessBand(score, label);
        const activityDate = context.activity_date || today.activity_date || context.latest_date || data.latest_date;
        const recoveryDate = context.recovery_date || today.recovery_date || activityDate;
        const latestLoad = today.latest_training_load || {};
        const sleepHours = sleep.asleep_hours ?? sleep.duration_hours;
        const stepsValue = today.steps;
        const azmValue = today.active_zone_minutes;
        const source = activityDate && recoveryDate && activityDate !== recoveryDate
          ? `Activity ${activityDate}; recovery ${recoveryDate}.`
          : activityDate ? `Health context from ${activityDate}.` : "Waiting for synced health context.";
        return {
          accent: readinessAccent(band),
          stateLabel: band,
          title: "Readiness",
          eyebrow: "mehair coach",
          date: source,
          chips: [readinessChip(label, score), activityDate].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: readiness.recommendation || data.recommendation || "Health context synced.",
          focusTitle: "Coach Take",
          focus: [readiness.recommendation || data.recommendation || "Health context synced."],
          metrics: [
            ["Steps", stepsValue != null ? `${intText(stepsValue)} steps` : null, activityDate ? `${activityDate} so far` : "latest window", "Movement load context, not a recovery score."],
            ["AZM", azmValue != null ? `${intText(azmValue)} min` : null, latestLoad.date && latestLoad.date !== activityDate ? `${latestLoad.active_zone_minutes ?? 0} on ${latestLoad.date}` : activityDate ? `${activityDate} so far` : "", "Fitbit hard-work minutes."],
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
        const freshness = data.data_freshness || {};
        const signalSnapshot = data.available_signal_snapshot || {};
        const score = finiteNumber(readiness.score ?? dataUsed.readiness_score, 0);
        const band = readinessBand(score, label);
        const coach = data.coach_response || {};
        const substitutions = data.substitutions || [];
        const planFocus = [
          ...(data.session_guidance || []).slice(0, 3),
          ...(data.focus || []).slice(0, 2),
        ];
        return {
          accent: readinessAccent(band),
          stateLabel: band,
          title: workoutTitle(data.planned_activity, data.recommended_intensity),
          eyebrow: "mehair coach",
          date: data.planned_date ? `Planned for ${data.planned_date}` : "Next planned session",
          chips: [intensityChip(data.recommended_intensity), rpeChip(data.rpe_cap), readinessChip(label, score), freshnessChip(freshness)].filter(Boolean),
          score,
          primaryLabel: "Readiness",
          headline: coach.short_answer || workoutHeadline(data),
          focusTitle: coach.session_blueprint ? "Session Blueprint" : "What To Do",
          focus: coach.session_blueprint || coach.what_to_do || planFocus,
          blocks: data.exercise_blocks || [],
          labels: coach.labels_explained || defaultLabelKey(["Readiness", "RPE", "HRV", "Resting HR", "AZM"]),
          metrics: [
            ["RPE cap", data.rpe_cap != null ? `${data.rpe_cap}/10` : null, rpePlain(data.rpe_cap)],
            ["Intensity", titleCase(data.recommended_intensity || ""), "", "The workout should feel this aggressive."],
            ["Sleep", dataUsed.sleep_asleep_hours != null ? `${num(dataUsed.sleep_asleep_hours, 1)}h` : null, dataUsed.sleep_sessions ? `${dataUsed.sleep_sessions} sessions` : ""],
            ["HRV", dataUsed.hrv_ms != null ? `${num(dataUsed.hrv_ms, 1)} ms` : null],
            ["Resting HR", dataUsed.resting_heart_rate ? `${dataUsed.resting_heart_rate} bpm` : null],
            ["Latest load", dataUsed.latest_training_load?.active_zone_minutes != null ? `${dataUsed.latest_training_load.active_zone_minutes} AZM` : null, dataUsed.latest_training_load?.date || "", "AZM = Fitbit hard-work minutes."],
          ],
          signalStrip: prioritySignalStrip(signalSnapshot.signals || []),
          evidenceTitle: "What This Means",
          evidence: [coach.data_story, ...(coach.why || data.limiting_factors || data.why || [])].filter(Boolean).slice(0, 5),
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
        const readinessScore = finiteNumber(readiness.score ?? dataUsed.readiness_score, 0);
        const readinessLabel = readiness.label || dataUsed.readiness_label;
        const readinessBandLabel = readinessBand(readinessScore, readinessLabel);
        const signalSnapshot = data.available_signal_snapshot || {};
        return {
          accent: safety.length ? "#a94f43" : readinessAccent(readinessBandLabel),
          stateLabel: readinessBandLabel,
          title: "Active Workout",
          eyebrow: "mehair coach",
          date: live.elapsed_minutes != null ? `${live.elapsed_minutes} min elapsed` : data.activity_date || "",
          chips: [
            decisionLabel(data.decision || "guidance"),
            live.current_heart_rate_bpm != null ? `${live.current_heart_rate_bpm} bpm` : "",
            live.current_rpe != null ? rpeChip(live.current_rpe) : "",
            live.pain_level != null ? `Pain ${live.pain_level}/10` : "",
            readinessChip(readinessLabel, readinessScore),
            freshnessChip(data.data_freshness || {}),
          ].filter(Boolean),
          score: readinessScore,
          showScore: !safety.length,
          primaryLabel: "Readiness",
          headline: coach.short_answer || data.headline || "Use live symptoms and effort to adjust the session.",
          focusTitle: activeWorkoutFocusTitle(data, coach, safety),
          focus: activeWorkoutFocus(data, coach, safety),
          labels: coach.labels_explained || defaultLabelKey(["HR", "RPE", "Readiness", "AZM"]),
          metrics: [
            ["Heart rate", live.current_heart_rate_bpm != null ? `${live.current_heart_rate_bpm} bpm` : null, hrMeaning(live.current_heart_rate_bpm, live.current_rpe)],
            ["RPE", live.current_rpe != null ? `${live.current_rpe}/10` : null, rpeMeaning(live.current_rpe)],
            ["Pain", live.pain_level != null ? `${live.pain_level}/10` : null, painMeaning(live.pain_level)],
            ["Elapsed", live.elapsed_minutes != null ? `${live.elapsed_minutes} min` : null],
            ["Readiness", readinessScore ? `${readinessScore}/100` : readinessLabel || null, readinessBandText(readinessScore, readinessLabel)],
            ["Latest load", dataUsed.latest_training_load?.active_zone_minutes != null ? `${dataUsed.latest_training_load.active_zone_minutes} AZM` : null, azmMeaning(dataUsed.latest_training_load?.active_zone_minutes), "AZM = Fitbit hard-work minutes from elevated heart-rate zones."],
          ],
          signalStrip: prioritySignalStrip(signalSnapshot.signals || []),
          evidenceTitle: safety.length ? "Safety Flags" : "Evidence",
          evidence: [coach.data_story, ...evidence].filter(Boolean),
          secondaryTitle: safety.length || coach.next_check ? "Next Check" : "Modify / Avoid",
          secondary: (coach.next_check || (safety.length ? coach.stop_if || safety : [...(data.modifications || []), ...(coach.avoid || data.avoid || [])])).slice(0, 5),
        };
      }

      function sleepModel(data) {
        const latest = data.latest || {};
        const freshness = data.data_freshness || {};
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
          eyebrow: "mehair coach",
          date: latest.date ? `Latest sleep from ${latest.date}` : "Latest synced sleep",
          chips: [`${sessions} session${sessions === 1 ? "" : "s"}`, freshnessChip(freshness)].filter(Boolean),
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
        const freshness = data.data_freshness || {};
        const highest = data.highest_load_day || {};
        const days = data.days || [];
        return {
          accent: "#7a6a18",
          title: "Activity Load",
          eyebrow: "mehair coach",
          date: rangeText(days),
          chips: [`${days.length || 0} days`, freshnessChip(freshness)].filter(Boolean),
          score: clamp(Math.round((Number(totals.active_zone_minutes || highest.active_zone_minutes || 0) / 150) * 100), 0, 100),
          primaryLabel: "Load",
          headline: `${intText(totals.steps ?? 0)} steps across the queried window.`,
          focusTitle: "Load Context",
          focus: highest.date ? [`${highest.date} had the highest zone-minute load in this window.`] : ["Latest synced activity load."],
          metrics: [
            ["Steps", `${intText(totals.steps ?? 0)} steps`, rangeText(days), "Total movement in this queried window."],
            ["Active", intText(totals.active_minutes ?? 0), "minutes"],
            ["AZM", `${intText(totals.active_zone_minutes ?? 0)} min`, rangeText(days), "Fitbit hard-work minutes across this window."],
            ["Highest AZM", highest.active_zone_minutes != null ? `${intText(highest.active_zone_minutes)} min` : null, highest.date || ""],
            ["Latest day", days.length ? days[days.length - 1].date : null],
            ["Distance", sumDistance(days)],
          ],
          evidenceTitle: "Evidence",
          evidence: highest.date ? [`${highest.date} was the highest load day.`] : [],
        };
      }

      function heartModel(data) {
        const days = data.days || [];
        const freshness = data.data_freshness || {};
        const latest = data.latest || days[days.length - 1] || {};
        const summary = data.summary || {};
        const score = latest.hrv_ms && summary.average_hrv_ms
          ? clamp(Math.round((latest.hrv_ms / summary.average_hrv_ms) * 75), 0, 100)
          : 50;
        return {
          accent: "#8a4b3e",
          title: "Heart Trends",
          eyebrow: "mehair coach",
          date: latest.date || rangeText(days),
          chips: ["heart", days.length ? `${days.length} days` : "", freshnessChip(freshness)].filter(Boolean),
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
        const freshness = data.data_freshness || {};
        const entries = Object.entries(metrics);
        return {
          accent: "#4b6f8f",
          title: "Returned Health Data",
          eyebrow: "mehair coach",
          date: data.start_date && data.end_date ? `${data.start_date} to ${data.end_date}` : "",
          chips: [`${data.requested_metrics.length} metrics`, data.source || "", freshnessChip(freshness)].filter(Boolean),
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

      function withDataWindow(model, data) {
        return { ...model, dataWindow: dataWindowFromPayload(data || {}, model || {}) };
      }

      function dataWindowFromPayload(data, model) {
        const source = data?.suggested_card || data || {};
        const freshness = source.data_freshness || source.freshness || source.context?.data_freshness || data.data_freshness || data.freshness || data.context?.data_freshness || {};
        const level = normalizedFreshnessLevel(freshness);
        const pullAge = pullAgeText(freshness);
        const latestDay = explicitLatestDateFromPayload(source) || explicitLatestDateFromPayload(data);
        const hasPullTimestamp = Boolean(freshness?.last_sync);
        const pull = pullAge && hasPullTimestamp
          ? `Latest Fitbit data pull was ${pullAge}`
          : pullAge
            ? `Fitbit pull timestamp unavailable; freshness says ${pullAge}`
            : "Fitbit timing unavailable for this card";
        const latest = latestDay
          ? `using Fitbit data through ${formatDayLabel(latestDay)}`
          : model.date
            ? `card window: ${model.date}`
            : "";
        return {
          level,
          levelLabel: level === "fresh" ? "Fresh pull" : level === "aging" ? "Aging pull" : level === "stale" ? "Stale pull" : "Fitbit timing",
          pull,
          latest,
        };
      }

      function pullAgeText(freshness) {
        const minutes = firstFinite(freshness?.sync_age_minutes, freshness?.age_minutes);
        if (freshness?.last_sync && minutes != null) return `at ${formatDateTime(freshness.last_sync)} (${ageMinutesText(minutes)})`;
        if (freshness?.last_sync) return `at ${formatDateTime(freshness.last_sync)}`;
        if (minutes != null) return ageMinutesText(minutes);
        if (freshness?.freshness_label) {
          const label = String(freshness.freshness_label).toLowerCase();
          if (label.includes("recommended")) return "not fresh; sync recommended";
          if (label.includes("stale")) return "more than 60 min ago";
          return freshness.freshness_label;
        }
        return freshnessChip(freshness || {});
      }

      function ageMinutesText(value) {
        const minutes = Math.max(0, Math.round(Number(value)));
        if (minutes < 1) return "just now";
        if (minutes < 60) return `${minutes} min ago`;
        const hours = Math.round(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        return `${Math.round(hours / 24)}d ago`;
      }

      function normalizedFreshnessLevel(freshness) {
        const explicit = String(freshness?.freshness_level || "").toLowerCase();
        if (["fresh", "aging", "stale"].includes(explicit)) return explicit;
        const minutes = firstFinite(freshness?.sync_age_minutes, freshness?.age_minutes);
        if (minutes != null) {
          if (minutes <= 15) return "fresh";
          if (minutes <= 60) return "aging";
          return "stale";
        }
        const label = String(freshness?.freshness_label || "").toLowerCase();
        if (label.includes("fresh")) return "fresh";
        if (label.includes("aging")) return "aging";
        if (label.includes("stale") || label.includes("recommended")) return "stale";
        return "unknown";
      }

      function explicitLatestDateFromPayload(data) {
        return latestIsoDate([
          data?.latest?.date,
          data?.today?.activity_date,
          data?.today?.recovery_date,
          data?.activity_date,
          data?.recovery_date,
          data?.latest_date,
          data?.data_used?.activity_date,
          data?.data_used?.recovery_date,
          data?.data_used?.latest_training_load?.date,
          data?.today?.latest_training_load?.date,
          data?.data_freshness?.latest_observed_date,
          data?.freshness?.latest_observed_date,
          data?.context?.data_freshness?.latest_observed_date,
        ]);
      }

      function explicitLatestDateFromModel(model) {
        return latestIsoDate([model?.date]);
      }

      function latestIsoDate(values) {
        const dates = [];
        for (const value of values || []) {
          const match = String(value || "").match(/\\d{4}-\\d{2}-\\d{2}/);
          if (match) dates.push(match[0]);
        }
        dates.sort();
        return dates[dates.length - 1] || "";
      }

      function formatDayLabel(value) {
        const match = String(value || "").match(/\\d{4}-\\d{2}-\\d{2}/);
        if (!match) return String(value || "");
        const [year, month, day] = match[0].split("-").map(Number);
        const parsed = new Date(year, month - 1, day);
        if (Number.isNaN(parsed.getTime())) return match[0];
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const deltaDays = Math.round((today.getTime() - parsed.getTime()) / 86400000);
        if (deltaDays === 0) return "Today";
        if (deltaDays === 1) return "Yesterday";
        return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      }

      function formatDateTime(value) {
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        });
      }

      function firstFinite(...values) {
        for (const value of values) {
          const number = Number(value);
          if (Number.isFinite(number)) return number;
        }
        return null;
      }

      function freshnessColor(level) {
        if (level === "fresh") return "#2f7a5f";
        if (level === "aging") return "#9b741c";
        if (level === "stale") return "#a94f43";
        return "#d63384";
      }

      function renderModel(model) {
        const accent = model.accent || "#d63384";
        const score = clamp(Math.round(Number(model.score || 0)), 0, 100);
        const isReadinessScore = String(model.primaryLabel || "").toLowerCase().includes("readiness");
        const band = isReadinessScore ? readinessBand(score, model.stateLabel || "") : "";
        const bandColor = isReadinessScore ? readinessBandColor(band) : accent;
        const syncColor = freshnessColor(model.dataWindow?.level);
        root.style.setProperty("--accent", "#d63384");
        root.style.setProperty("--accent-soft", "#fff0f7");
        root.style.setProperty("--state", "#d63384");
        root.style.setProperty("--state-soft", "#fff0f7");
        root.style.setProperty("--band-color", bandColor);
        root.style.setProperty("--band-soft", softFor(bandColor));
        root.style.setProperty("--sync-dot", syncColor);
        root.style.setProperty("--sync-soft", softFor(syncColor));
        root.style.setProperty("--score", String(score));
        const primaryFocus = listItems(model.focus, "Health context synced.");
        const secondaryTitle = model.secondaryTitle || "Evidence";
        const secondary = model.secondary || model.evidence || [];
        const blocks = renderBlocks(model.blocks);
        const scoreContext = scoreNote(model.primaryLabel, score);
        const stateLabel = isReadinessScore ? readinessStateLabel(model.stateLabel || readinessBand(score, "")) : "";
        const showScore = model.showScore !== false && isReadinessScore;
        root.innerHTML = `
          <div class="mast">
            <div class="identity">
              <p class="eyebrow">${escapeHtml(model.eyebrow || "mehair coach")}</p>
              <h1>${escapeHtml(model.title || "mehair coach")}</h1>
              <p class="headline">${escapeHtml(model.headline || "Health context synced.")}</p>
            </div>
            <div class="stamp">${escapeHtml(model.date || "")}</div>
          </div>
          <div class="status-row">
            ${(model.chips || ["health"]).slice(0, 4).map((item, index) => `<span class="chip ${index === 0 ? "accent" : ""}">${escapeHtml(item)}</span>`).join("")}
          </div>
          ${renderDataWindow(model.dataWindow)}
          <div class="hero ${showScore ? "" : "no-score"}">
            ${showScore ? `
              <div class="score-card">
                <div class="gauge" aria-label="${escapeHtml(model.primaryLabel || "score")} ${score}">
                  <div class="gauge-inner">
                    <b>${escapeHtml(score)}</b>
                    <span>${escapeHtml(model.primaryLabel || "Score")}</span>
                  </div>
                </div>
                ${stateLabel ? `<span class="score-state">${escapeHtml(stateLabel)}</span>` : ""}
                ${scoreContext ? `<p class="score-note">${escapeHtml(scoreContext)}</p>` : ""}
                ${isReadinessScore ? `<div class="band-legend" aria-label="Readiness thresholds"><span class="band-green">green 75+</span><span class="band-yellow">yellow 55-74</span><span class="band-red">red &lt;55</span></div>` : ""}
              </div>
            ` : ""}
            <div class="plan-box">
              <h2>${escapeHtml(model.focusTitle || "Coach Take")}</h2>
              ${renderDoseCue(model)}
              <ul class="focus-list">${primaryFocus}</ul>
            </div>
          </div>
          ${blocks}
          <div class="metrics">
            ${(model.metrics || []).slice(0, 6).map((item) => metric(item[0], item[1], item[2], item[3])).join("")}
          </div>
          ${renderSignalStrip(model.signalStrip)}
          ${renderLabelKey(model.labels || inferredLabelKey(model))}
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

      function renderDataWindow(dataWindow) {
        if (!dataWindow || (!dataWindow.pull && !dataWindow.latest)) return "";
        const label = dataWindow.levelLabel || "Fitbit timing";
        const text = [dataWindow.pull, dataWindow.latest].filter(Boolean).join(" · ");
        return `<div class="data-window" aria-label="Fitbit data timing"><b>${escapeHtml(label)}</b><span>${escapeHtml(text)}</span></div>`;
      }

      function renderDoseCue(model) {
        const cue = model?.doseCue || minimumDoseCue(model);
        if (!cue) return "";
        return `<div class="dose-cue">${escapeHtml(cue)}</div>`;
      }

      function minimumDoseCue(model) {
        const text = [
          model?.title,
          model?.headline,
          ...(model?.chips || []),
          ...(model?.focus || []),
          ...(model?.evidence || []),
          ...(model?.secondary || []),
        ].filter(Boolean).join(" ").toLowerCase();
        const isWorkout = /workout|session|movement|training|rpe|intensity|planned/.test(text);
        const hasMinimumDose = /smallest useful dose|minimum useful|minimum effective|leave energy|finish with energy|before class|before work|next obligation|what comes next|breathing calm|focus intact|not wrecked|compact and useful/.test(text);
        if (!isWorkout || !hasMinimumDose) return "";
        if (/class|meeting|work|shift|obligation|what comes next|breathing calm|focus intact|cool down and reset/.test(text)) {
          return "Minimum useful dose: leave energy for what comes next.";
        }
        if (/short|compact|time box|between meetings|not wrecked/.test(text)) {
          return "Compact useful dose: finish with one gear unused.";
        }
        return "Minimum useful dose: enough work to feel better, not a workout to recover from.";
      }

      const LABEL_KEY_PRIORITY = ["Readiness", "RPE", "AZM", "HRV", "Resting HR", "SpO2", "Respiratory rate", "HR", "VO2 max", "Sleep temperature"];

      function prioritizedLabelKey(labels) {
        const seen = new Set();
        return (labels || [])
          .filter((item) => item && item.label && item.meaning)
          .filter((item) => {
            if (seen.has(item.label)) return false;
            seen.add(item.label);
            return true;
          })
          .sort((a, b) => {
            const aIndex = LABEL_KEY_PRIORITY.indexOf(a.label);
            const bIndex = LABEL_KEY_PRIORITY.indexOf(b.label);
            const aRank = aIndex === -1 ? 999 : aIndex;
            const bRank = bIndex === -1 ? 999 : bIndex;
            return aRank - bRank;
          });
      }

      function renderLabelKey(labels) {
        const usable = prioritizedLabelKey(labels).slice(0, 6);
        if (!usable.length) return "";
        return `
          <div class="label-key" aria-label="Metric label explanations">
            <div class="label-heading">Metric labels, translated</div>
            ${usable.map((item) => `
              <div class="label-pill">
                <b>${escapeHtml(item.label)}</b>
                <span>${escapeHtml(item.meaning)}</span>
              </div>
            `).join("")}
          </div>
        `;
      }

      function inferredLabelKey(model) {
        const metricLabels = (model?.metrics || []).map((item) => item?.[0]);
        const signalLabels = (model?.signalStrip || []).map((item) => item?.label);
        const text = [
          model?.primaryLabel,
          model?.headline,
          ...(metricLabels || []),
          ...(signalLabels || []),
          ...(model?.focus || []),
          ...(model?.evidence || []),
          ...(model?.secondary || []),
        ].filter(Boolean).join(" ").toLowerCase();
        const labels = [];
        if (text.includes("readiness")) labels.push("Readiness");
        if (/\\brpe\\b|perceived exertion/.test(text)) labels.push("RPE");
        if (/\\bhrv\\b|heart-rate variability/.test(text)) labels.push("HRV");
        if (/resting hr|\\brhr\\b|resting heart/.test(text)) labels.push("Resting HR");
        if (/\\bazm\\b|active zone|zone-minute|zone minutes|training load|\\bload\\b/.test(text)) labels.push("AZM");
        if (/spo2|oxygen saturation|oxygen/.test(text)) labels.push("SpO2");
        if (/respiratory rate|breaths per minute/.test(text)) labels.push("Respiratory rate");
        if (/vo2 max|cardio capacity/.test(text)) labels.push("VO2 max");
        if (/sleep temperature|temperature change/.test(text)) labels.push("Sleep temperature");
        return defaultLabelKey(dedupe(labels));
      }

      function renderSignalStrip(signals) {
        const usable = (signals || []).filter((item) => item && item.label).slice(0, 6);
        if (!usable.length) return "";
        return `
          <div class="signal-heading">Other signals checked for this answer</div>
          <div class="signal-strip" aria-label="Signals checked">
            ${usable.map((item) => `
              <div class="signal-card">
                <b>${escapeHtml(item.label)}</b>
                <span>${escapeHtml([item.display || item.latest || "synced", item.latest_date || item.window || ""].filter(Boolean).join(" · "))}</span>
                <small>${escapeHtml(item.coaching_use || item.why_it_matters || metricHint(item.label))}</small>
              </div>
            `).join("")}
          </div>
        `;
      }

      function metric(label, value, detail, explanation) {
        const detailHtml = detail ? `<small>${escapeHtml(detail)}</small>` : "";
        const explain = explanation || metricHint(label);
        const explainHtml = explain ? `<em>${escapeHtml(explain)}</em>` : "";
        return `<div class="metric"><b>${escapeHtml(value ?? "Not synced")}</b><span>${escapeHtml(label)}</span>${detailHtml}${explainHtml}</div>`;
      }

      function signalMetric(signal, fallbackDate) {
        const label = signal.label || titleCase(signal.id || "signal");
        const detail = signal.latest_date || signal.window || signal.category || fallbackDate || "";
        const explanation = signal.coaching_use || signal.why_it_matters || metricHint(label);
        return [label, signal.display ?? signal.latest, detail, explanation];
      }

      function prioritySignalStrip(signals) {
        const priority = [
          "spo2",
          "respiratory_rate",
          "sleep_temperature",
          "vo2_max",
          "heart_rate_zones",
          "active_zone_minutes",
          "steps",
          "sleep",
          "hrv",
          "resting_heart_rate",
        ];
        const rank = (signal) => {
          const id = String(signal.id || "").toLowerCase();
          const index = priority.indexOf(id);
          return index >= 0 ? index : priority.length;
        };
        return (signals || [])
          .filter((item) => item && (item.display || item.latest != null))
          .sort((a, b) => rank(a) - rank(b))
          .slice(0, 6)
          .map((item) => ({
            label: item.label || titleCase(item.id || "Signal"),
            display: item.display ?? item.latest,
            coaching_use: item.coaching_use || item.why_it_matters || metricHint(item.label || item.id),
            latest_date: item.latest_date || item.window || "",
            why_it_matters: item.why_it_matters || "",
          }));
      }

      function activeWorkoutFocusTitle(data, coach, safety) {
        const decision = String(data.decision || "").toLowerCase();
        const hasActions = (coach.what_to_do || data.immediate_actions || []).filter(Boolean).length > 0;
        const actionText = [
          decision,
          data.headline || "",
          coach.short_answer || "",
          ...(coach.what_to_do || []),
          ...(data.immediate_actions || []),
        ].join(" ").toLowerCase();
        if (safety.length || decision.includes("stop")) return "Stop Hard Work Now";
        if (decision.includes("downshift") || /\\b(back off|ease up|reduce|cut|lower)\\b/.test(actionText)) return "Back Off Now";
        if (decision.includes("modify") || /\\b(adjust|modify|substitute|change the movement)\\b/.test(actionText)) return "Adjust This Block";
        if (
          decision.includes("continue") ||
          decision.includes("controlled") ||
          /\\b(hold steady|hold this effort|same pace|stay at or below|keep the exact same|do not surge)\\b/.test(actionText)
        ) return "Hold This Effort";
        return hasActions ? "Next Action" : "Coach Take";
      }

      function activeWorkoutFocus(data, coach, safety) {
        const live = data.live_inputs || {};
        const decision = String(data.decision || "").toLowerCase();
        const base = coach.what_to_do || data.immediate_actions || [];
        const concrete = [];
        if (!safety.length && decision.includes("continue") && (live.current_rpe != null || live.current_heart_rate_bpm != null)) {
          const targets = [
            live.current_rpe != null ? `RPE ${live.current_rpe}/10 or easier` : "",
            live.current_heart_rate_bpm != null ? `around ${live.current_heart_rate_bpm} bpm or lower` : "",
          ].filter(Boolean).join(" and ");
          concrete.push(`Next 5-10 minutes: hold steady at ${targets}; do not surge yet.`);
        }
        if (!safety.length && (decision.includes("modify") || decision.includes("downshift"))) {
          concrete.push("Next block: reduce pace, load, or reps first; only build back up if breathing and form normalize.");
        }
        return dedupe([...concrete, ...base]).slice(0, 5);
      }

      function dedupe(items) {
        const seen = new Set();
        const result = [];
        for (const item of items || []) {
          const key = String(item || "").trim();
          if (!key || seen.has(key)) continue;
          seen.add(key);
          result.push(key);
        }
        return result;
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
        const note = [block.note || "", block.alternative ? `Alt: ${block.alternative}` : ""]
          .filter(Boolean)
          .join(" ");
        return `
          <div class="workout-block">
            <b>${escapeHtml(name)}</b>
            ${renderPrescriptionPills(block)}
            ${note ? `<small>${escapeHtml(note)}</small>` : ""}
          </div>
        `;
      }

      function renderPrescriptionPills(block) {
        const pills = [
          { label: "Sets", value: block.sets },
          { label: "Reps", value: block.reps },
          { label: "Effort", value: explainPrescription(block.intensity || "") },
        ].filter((item) => item.value);
        if (!pills.length) return "";
        return `
          <div class="workout-prescription" aria-label="Exercise prescription">
            ${pills.map((item) => `
              <span class="rx-pill">
                <b>${escapeHtml(item.label)}</b>
                <span>${escapeHtml(item.value)}</span>
              </span>
            `).join("")}
          </div>
        `;
      }

      function freshnessChip(freshness) {
        if (!freshness || !freshness.freshness_level) return "";
        if (freshness.freshness_level === "fresh") return "fresh <15m";
        if (freshness.freshness_level === "aging") return "aging 15-60m";
        if (freshness.freshness_level === "stale") return "stale >60m";
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

      function readinessChip(label, score) {
        const band = readinessBand(score, label);
        const scoreText = Number.isFinite(Number(score)) && Number(score) > 0 ? `${Math.round(Number(score))}/100: ` : "";
        const clean = titleCase(band || label || "pending");
        if (band === "green") return `${scoreText}${clean} 75+ supports training`;
        if (band === "yellow") return `${scoreText}${clean} 55-74 keep controlled`;
        if (band === "red") return `${scoreText}${clean} <55 recovery first`;
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

      function rpeMeaning(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "";
        if (number <= 4) return "easy enough to talk normally";
        if (number <= 6) return "controlled; useful work without grinding";
        if (number <= 7) return "hard but still managed";
        if (number <= 8) return "challenging; hold or back off, do not push higher";
        return "very hard; downshift unless this was planned";
      }

      function hrMeaning(value, rpe) {
        if (value == null) return "";
        if (rpe != null && Number(rpe) >= 8) return "Use with RPE: if it keeps climbing at the same pace, ease off.";
        return "Current beats per minute; useful when compared with effort and symptoms.";
      }

      function painMeaning(value) {
        if (value == null) return "";
        const number = Number(value);
        if (!Number.isFinite(number)) return "";
        if (number <= 3) return "acceptable only if it stays steady and does not change form";
        if (number <= 6) return "modify now; pain should not climb during training";
        return "stop loading the painful movement";
      }

      function azmMeaning(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "Fitbit hard-work minutes from elevated heart-rate zones.";
        if (number < 15) return "light load so far; useful context, not a reason to chase intensity";
        if (number < 45) return "moderate load; count it before adding more hard work";
        if (number < 70) return "high load; bias the rest of the day controlled";
        return "very high load; recovery matters more than adding intensity";
      }

      function readinessBandText(score, label) {
        const number = Number(score);
        const lower = String(label || "").toLowerCase();
        if (Number.isFinite(number) && number > 0) {
          if (number >= 75) return "green today (75+); yellow is 55-74, red is <55";
          if (number >= 55) return "yellow today (55-74); green is 75+, red is <55";
          return "red today (<55); make recovery the main workout";
        }
        if (lower === "green") return "green means 75+; still obey pain, symptoms, and RPE";
        if (lower === "yellow") return "yellow means 55-74; avoid max efforts";
        if (lower === "red") return "red means <55; recovery first";
        return "Readiness blends sleep, heart, and load signals.";
      }

      function scoreNote(primaryLabel, score) {
        const label = String(primaryLabel || "").toLowerCase();
        if (label.includes("readiness")) {
          return "Readiness thresholds: green 75+, yellow 55-74, red <55. Pain, dizziness, or feeling sick overrides the score.";
        }
        if (label.includes("load")) return "Higher load means more recovery cost, especially for legs and intervals.";
        if (label.includes("sleep")) return "This is a sleep target cue, not a medical score.";
        return "";
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
          return `Make this an easy session that supports recovery and leaves energy in reserve.${cap}`;
        }
        if (String(data.recommended_intensity || data.intensity || "").includes("moderate")) {
          return `Do a useful ${intensity.toLowerCase()} session, not a prove-it workout.${cap}`;
        }
        return data.summary || data.recommendation || `Recovery can support training today.${cap}`;
      }

      function metricHint(label) {
        const lower = String(label || "").toLowerCase();
        if (lower.includes("rpe")) return "RPE = how hard it feels: 1 easy, 10 max; use it to cap effort.";
        if (lower.includes("intensity")) return "How aggressive the workout should feel.";
        if (lower.includes("hrv")) return "HRV = recovery stress signal compared with your usual.";
        if (lower === "heart rate") return "HR = current beats per minute.";
        if (lower.includes("resting") || lower.includes("rhr")) return "Resting HR = heart stress signal at rest.";
        if (lower.includes("load") || lower.includes("azm") || lower.includes("zone")) return "AZM = Fitbit hard-work minutes; higher AZM means more recent load to recover from.";
        if (lower.includes("sleep")) return "Sleep is the biggest recovery input.";
        if (lower.includes("spo2") || lower.includes("oxygen")) return "SpO2 = oxygen saturation; useful breathing context, not a standalone green light.";
        if (lower.includes("resp")) return "Respiratory rate = breaths per minute; unusual changes can hint stress, illness, or recovery strain.";
        if (lower.includes("temperature") || lower.includes("temp")) return "Sleep temperature change can hint body stress when it differs from your usual.";
        if (lower.includes("vo2")) return "VO2 max estimates cardio capacity; it changes slowly and is not today's stop/go signal.";
        if (lower.includes("steps")) return "Steps are movement load for this window, especially useful for leg fatigue.";
        if (lower.includes("readiness")) return "Readiness blends sleep, heart, and load: green 75+, yellow 55-74, red <55.";
        if (lower.includes("move")) return "Today's movement, not the whole week.";
        if (lower.includes("soreness")) return "Your check-in can override good wearable scores.";
        if (lower.includes("goal")) return "Goal pressure comes after recovery signals.";
        if (lower.includes("vitals")) return "Extra recovery context from Fitbit.";
        return "";
      }

      function defaultLabelKey(labels) {
        const meanings = {
          "Readiness": "sleep, heart, and recent load blended into one recovery cue; green 75+, yellow 55-74, red <55",
          "RPE": "how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop",
          "HR": "heart rate right now, in beats per minute",
          "HRV": "recovery stress signal compared with your usual",
          "Resting HR": "heart stress signal at rest",
          "AZM": "Fitbit hard-work minutes from elevated heart-rate zones; recent load that should change how hard you push",
          "SpO2": "oxygen saturation from Fitbit; useful breathing context, not a standalone reason to train hard",
          "Respiratory rate": "breaths per minute, mostly useful when it changes from your usual or matches symptoms",
          "VO2 max": "cardio capacity estimate that changes slowly, not a same-day green light",
          "Sleep temperature": "temperature change during sleep, useful as a secondary stress or illness clue",
        };
        return (labels || []).map((label) => ({ label, meaning: meanings[label] })).filter((item) => item.meaning);
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
        if (text.includes("AZM") && !text.includes("hard-work minutes")) {
          text = text.replaceAll("AZM", "AZM (Fitbit hard-work minutes)");
        }
        if (text.includes("SpO2") && !text.includes("oxygen saturation")) {
          text = text.replaceAll("SpO2", "SpO2 (oxygen saturation)");
        }
        if (text.includes("RPE") && !text.includes("how hard it feels")) {
          text = text.replaceAll("RPE", "RPE (how hard it feels)");
        }
        return text;
      }

      function explainPrescription(value) {
        const text = String(value || "");
        const match = text.match(/RPE\\s*<=\\s*(\\d+)/i);
        if (!match) return text;
        return `${text} (${rpePlain(match[1])})`;
      }

      function readinessBand(score, label) {
        const number = Number(score);
        if (Number.isFinite(number) && number > 0) {
          if (number >= 75) return "green";
          if (number >= 55) return "yellow";
          return "red";
        }
        const lower = String(label || "").toLowerCase();
        if (["green", "yellow", "red"].includes(lower)) return lower;
        return lower || "pending";
      }

      function readinessStateLabel(label) {
        const lower = String(label || "").toLowerCase();
        if (lower === "green") return "Training room, not automatic go (75+)";
        if (lower === "yellow") return "Controlled work (55-74)";
        if (lower === "red") return "Recovery first (<55)";
        return "";
      }

      function readinessAccent(label) {
        return "#d63384";
      }

      function readinessBandColor(label) {
        const band = readinessBand(null, label);
        if (band === "green") return "#2f7a5f";
        if (band === "yellow") return "#9b741c";
        if (band === "red") return "#a94f43";
        return "#d63384";
      }

      function softFor(accent) {
        const map = {
          "#2f7a5f": "#edf5f0",
          "#d63384": "#fff0f7",
          "#c02673": "#fff0f6",
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

      function dateRangeDays(start, end) {
        if (!start || !end) return 0;
        const startDate = new Date(`${start}T00:00:00Z`);
        const endDate = new Date(`${end}T00:00:00Z`);
        if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return 0;
        return Math.max(1, Math.round((endDate - startDate) / 86400000) + 1);
      }

      function compactRangeLabel(dateRange, days) {
        const safeDays = finiteNumber(days, 0);
        if (safeDays > 1) return `last ${safeDays} days`;
        if (dateRange?.start && dateRange?.end && dateRange.start !== dateRange.end) return `${dateRange.start} to ${dateRange.end}`;
        if (dateRange?.end || dateRange?.start) return dateRange.end || dateRange.start;
        return "";
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

      function decisionLabel(value) {
        const labels = {
          stop_and_assess: "Stop + Assess",
          stop_session: "End Session",
          downshift_now: "Back Off Now",
          continue_controlled: "Continue Controlled",
          modify: "Modify",
        };
        return labels[value] || titleCase(value || "guidance");
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
                "What should I focus on today based on my data?",
                "I only have 30 minutes. What is the best use of it?",
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
                "averages": {"steps_per_day": 5886, "active_zone_minutes_per_day": 10.3},
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
        "available_signal_snapshot": {
            "status": "ok",
            "available_signal_ids": ["spo2", "respiratory_rate", "sleep_temperature", "vo2_max", "heart_rate_zones"],
            "signals": [
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "98.1%",
                    "latest": 98.1,
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Oxygen context helps explain breathing and recovery, but it is not a green light by itself.",
                    "coaching_use": "Use with respiratory rate, symptoms, and effort before deciding to push hard.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "17.2/min",
                    "latest": 17.2,
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Breathing rate can rise with stress, illness, poor sleep, or hard recent training.",
                    "coaching_use": "If this is up with bad sleep or symptoms, make the day easier.",
                },
                {
                    "id": "sleep_temperature",
                    "label": "Sleep temperature",
                    "display": "+0.4 C",
                    "latest_date": "2026-07-03",
                    "category": "recovery",
                    "why_it_matters": "Temperature shifts are secondary clues for body stress.",
                    "coaching_use": "Treat a clear rise as a reason to avoid max-effort work.",
                },
                {
                    "id": "vo2_max",
                    "label": "VO2 max",
                    "display": "43.6",
                    "latest": 43.6,
                    "latest_date": "2026-07-03",
                    "category": "capacity",
                    "why_it_matters": "Cardio capacity changes slowly and helps set training direction.",
                    "coaching_use": "Use for long-term fitness trends, not as today's green light.",
                },
                {
                    "id": "heart_rate_zones",
                    "label": "Heart zones",
                    "display": "72 AZM",
                    "latest": 72,
                    "latest_date": "2026-07-02",
                    "category": "training_load",
                    "why_it_matters": "Zone minutes show how much hard work your body already absorbed.",
                    "coaching_use": "High recent AZM should cap extra intensity today.",
                },
            ],
        },
        "data_used": {"synced_metric_count": 9},
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 7,
            "last_sync": "2026-07-03T11:53:00+00:00",
        },
    },
    "health-clues": {
        "status": "ok",
        "clue_type": "health_question_clues",
        "question": "I feel cooked today. Which metrics matter?",
        "headline": "Recovery looks limited today: short sleep is lining up with weaker heart signals.",
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
                "reason": "Daily HRV helps spot recovery changes versus your usual.",
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
        "available_signal_snapshot": {
            "status": "ok",
            "available_signal_ids": ["sleep", "hrv", "resting_heart_rate", "spo2", "respiratory_rate", "active_zone_minutes"],
            "signals": [
                {
                    "id": "sleep",
                    "label": "Sleep",
                    "display": "5.1h",
                    "latest_date": "2026-07-03",
                    "category": "recovery",
                    "why_it_matters": "Short sleep is one of the clearest reasons to cap intensity.",
                    "coaching_use": "Make hard training earn its place only if the rest of the signals look good.",
                },
                {
                    "id": "hrv",
                    "label": "HRV",
                    "display": "36 ms",
                    "latest_date": "2026-07-03",
                    "category": "heart",
                    "why_it_matters": "HRV below your usual can mean your body is under more stress.",
                    "coaching_use": "Use it to cap RPE and choose controlled work.",
                },
                {
                    "id": "resting_heart_rate",
                    "label": "Resting HR",
                    "display": "67 bpm",
                    "latest_date": "2026-07-03",
                    "category": "heart",
                    "why_it_matters": "Resting HR above usual can point to fatigue, stress, or illness.",
                    "coaching_use": "Elevated resting HR makes max-effort work less attractive.",
                },
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "98.1%",
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Oxygen looks reassuring here, but it should not overrule sleep, HRV, soreness, or symptoms.",
                    "coaching_use": "Useful context for breathing questions; not a standalone go signal.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "17.2/min",
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Breathing rate helps explain recovery when it changes from your usual.",
                    "coaching_use": "Pair it with SpO2, sleep, and symptoms.",
                },
                {
                    "id": "active_zone_minutes",
                    "label": "AZM",
                    "display": "72 min",
                    "latest_date": "2026-07-02",
                    "category": "training_load",
                    "why_it_matters": "Active Zone Minutes are recent hard-work minutes your body must recover from.",
                    "coaching_use": "High recent load should reduce extra intensity.",
                },
            ],
        },
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
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 7,
            "last_sync": "2026-07-03T11:53:00+00:00",
        },
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
            "data_story": "The useful read: sleep is limiting recovery; HRV is lower than usual; Resting HR is elevated.",
            "session_blueprint": [
                "Start with 10 minutes easy walking, cycling, or mobility to see if you feel better.",
                "Then do 10-25 minutes easy movement at RPE <= 6/10; stop before it feels like work.",
                "Finish while you feel better than when you started.",
            ],
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
            "labels_explained": [
                {"label": "Readiness", "meaning": "a quick recovery score built from sleep, heart, and recent load signals; green 75+, yellow 55-74, red <55"},
                {"label": "RPE", "meaning": "how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop"},
                {"label": "HRV", "meaning": "recovery stress signal compared with your usual"},
                {"label": "AZM", "meaning": "Fitbit hard-work minutes from elevated heart-rate zones; recent load that should change how hard you push"},
            ],
            "stop_if": [
                "Stop if pain rises above 3/10, becomes sharp, or changes your form.",
                "End early if the warm-up does not make you feel better within 10-15 minutes.",
            ],
            "avoid": ["Loading sore areas aggressively", "Another hard conditioning block today"],
        },
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 7,
            "last_sync": "2026-07-03T11:53:00+00:00",
        },
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
            "data_story": "The useful read: HRV is lower than usual; Resting HR is elevated; recent training load matters today.",
            "session_blueprint": [
                "Warm-up: 5-8 minutes easy cardio to check readiness.",
                "Main work: Machine chest press, Chest-supported row, Neutral-grip lat pulldown; keep every set at RPE <= 6/10.",
                "Keep working sets at or below RPE 6/10 (comfortable, should not feel like a grind).",
                "Main coaching cue: Prefer chest-supported rows, pulldowns, and cable work.",
            ],
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
            "labels_explained": [
                {"label": "Readiness", "meaning": "a quick recovery score built from sleep, heart, and recent load signals; green 75+, yellow 55-74, red <55"},
                {"label": "RPE", "meaning": "how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop"},
                {"label": "HRV", "meaning": "recovery stress signal compared with your usual"},
                {"label": "Resting HR", "meaning": "heart stress signal at rest, best judged against your usual"},
            ],
            "avoid": ["Heavy deadlifts", "Heavy bent-over rows", "Aggressive bench arch if low back feels sensitive"],
        },
        "available_signal_snapshot": {
            "status": "ok",
            "signals": [
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "98.6%",
                    "latest_date": "2026-07-03",
                    "coaching_use": "Use low or unusual SpO2 with respiratory rate, resting HR, sleep, and symptoms to lower intensity or recommend caution.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "18.6 breaths/min",
                    "latest_date": "2026-07-03",
                    "coaching_use": "Use elevated or unusual respiratory rate as a reason to cap intensity, especially with symptoms or low sleep.",
                },
                {
                    "id": "heart_rate_zones",
                    "label": "Heart-rate zones",
                    "display": "63 AZM",
                    "latest_date": "2026-07-02",
                    "coaching_use": "Use zone minutes as the hard-work load signal for whether to push or preserve energy.",
                },
            ],
        },
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 9,
            "last_sync": "2026-07-03T11:51:00+00:00",
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
            "data_story": "The useful read: live symptoms override the workout plan.",
            "next_check": [
                "Next 3-5 minutes: stop hard work, breathe normally, and let heart rate and symptoms settle.",
                "Do not restart hard training today if symptoms are new, severe, or return.",
                "Seek urgent help for chest pain, fainting, severe shortness of breath, or worsening symptoms.",
            ],
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
            "labels_explained": [
                {"label": "HR", "meaning": "heart rate right now, in beats per minute"},
                {"label": "RPE", "meaning": "how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop"},
                {"label": "Readiness", "meaning": "a quick recovery score built from sleep, heart, and recent load signals; green 75+, yellow 55-74, red <55"},
                {"label": "AZM", "meaning": "Fitbit hard-work minutes from elevated heart-rate zones; recent load that should change how hard you push"},
            ],
            "stop_if": [
                "Stop if symptoms are new, severe, or worsening.",
                "Stop if heart rate or breathing does not settle after 3-5 easy minutes.",
                "Stop if pain rises above 3/10 or changes your form.",
            ],
        },
        "available_signal_snapshot": {
            "status": "ok",
            "signals": [
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "97.8%",
                    "latest_date": "2026-07-03",
                    "coaching_use": "Background breathing/oxygen context; not live workout telemetry.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "18.1 breaths/min",
                    "latest_date": "2026-07-03",
                    "coaching_use": "Background breathing stress context from synced sleep data.",
                },
            ],
        },
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 11,
            "last_sync": "2026-07-03T11:49:00+00:00",
        },
        "safety_note": "This is in-session fitness guidance, not medical diagnosis or emergency care.",
    },
    "active-workout-hold": {
        "status": "ok",
        "guidance_type": "active_workout_guidance",
        "planned_activity": "Run",
        "decision": "continue_controlled",
        "headline": "Hold steady until 27-32 minutes elapsed; do not make the workout harder yet.",
        "immediate_actions": [
            "Stay at or below RPE 7/10 until 27-32 minutes elapsed.",
            "Keep the exact same pace, load, or resistance; no sprint, PR, or surprise finisher.",
            "Stay below the point where form, breathing, or coordination changes.",
        ],
        "modifications": [
            "If heart rate climbs while the pace feels the same, back off for 3-5 easy minutes.",
            "If RPE rises by 1 point or breathing stops feeling controlled, reduce speed, load, or impact one notch.",
        ],
        "avoid": ["Adding surprise max-effort work", "Ignoring new pain or unusual symptoms"],
        "safety_flags": [],
        "evidence": [
            "Live heart rate reported: 150 bpm (HR = current beats per minute).",
            "Live effort reported: RPE 7/10 (RPE = how hard it feels).",
            "Live pain reported: 0/10.",
            "Latest synced load before/during this decision: 23 Active Zone Minutes on 2026-07-03 (AZM, Fitbit hard-work minutes).",
        ],
        "readiness": {"score": 78, "label": "green"},
        "data_freshness": {
            "freshness_level": "aging",
            "freshness_label": "aging 15-60 min",
            "latest_observed_date": "2026-07-03",
            "age_minutes": 18,
            "last_sync": "2026-07-03T11:42:00+00:00",
        },
        "live_inputs": {
            "current_heart_rate_bpm": 150,
            "current_rpe": 7,
            "pain_level": 0,
            "symptoms": "no dizziness, breathing controlled",
            "elapsed_minutes": 22,
            "planned_duration_minutes": 40,
        },
        "data_used": {
            "readiness_score": 78,
            "readiness_label": "green",
            "sleep_asleep_hours": 9.4,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 23},
        },
        "coach_response": {
            "short_answer": "Keep going, but hold the effort steady and reassess before you add intensity.",
            "data_story": "The useful read: sleep supports training; recent load is manageable; breathing and oxygen signals are background context, not a standalone green light.",
            "what_to_do": [
                "Next 5-10 minutes: hold steady at RPE (how hard it feels) 7/10 or easier and around 150 bpm or lower; do not surge yet.",
                "Hold steady until 27-32 minutes elapsed; do not make the workout harder yet.",
                "Stay at or below RPE (how hard it feels) 7/10 until 27-32 minutes elapsed.",
            ],
            "next_check": [
                "Next 5-10 minutes: hold steady instead of chasing a harder effort.",
                "Keep RPE (how hard it feels) at or below 7/10 unless the plan intentionally calls for more.",
                "Heart rate should rise and settle predictably for the work you are doing.",
            ],
            "why": [
                "Latest sleep is strong at 9.4h. Good sleep gives more room to train, as long as the warm-up agrees.",
                "Resting HR is not elevated, which supports normal training.",
                "Recent load is moderate, so do not add a surprise hard finish.",
            ],
            "labels_explained": [
                {"label": "HR", "meaning": "heart rate right now: current beats per minute during movement or rest"},
                {"label": "RPE", "meaning": "rate of perceived exertion: how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop"},
                {"label": "AZM", "meaning": "Active Zone Minutes: Fitbit's hard-work minutes from elevated heart-rate zones; recent AZM is load you need to recover from"},
                {"label": "Readiness", "meaning": "a quick recovery score built from sleep, heart, and recent load signals; green is 75+, yellow is 55-74, red is below 55"},
            ],
        },
        "live_data_note": "In-session guidance uses user-reported live HR/RPE/pain plus the latest cloud-synced Fitbit context; it is not direct band telemetry.",
        "safety_note": "This is in-session fitness guidance, not medical diagnosis or emergency care.",
    },
    "recovery-comparison": {
        "status": "ok",
        "comparison_type": "sleep_heart_recovery",
        "headline": "Recovery looks limited today: short sleep is lining up with weaker heart signals.",
        "date_range": {"start": "2026-06-30", "end": "2026-07-03"},
        "window_days": 7,
        "latest": {
            "date": "2026-07-03",
            "sleep_hours": 5.1,
            "hrv_ms": 36,
            "resting_heart_rate": 67,
            "active_zone_minutes": 0,
            "spo2_avg": 98.1,
            "respiratory_rate": 17.2,
            "sleep_temperature": {"delta_celsius": 0.4},
        },
        "baseline": {
            "sleep_hours": 7.3,
            "hrv_ms": 56.5,
            "resting_heart_rate": 57.5,
            "active_zone_minutes": 42,
            "spo2_avg": 97.8,
            "respiratory_rate": 16.1,
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
        "available_signal_snapshot": {
            "status": "ok",
            "available_signal_ids": ["sleep", "hrv", "resting_heart_rate", "spo2", "respiratory_rate", "sleep_temperature"],
            "signals": [
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "98.1%",
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Reassuring oxygen context, but not enough alone to train hard.",
                    "coaching_use": "Use as one secondary breathing clue.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "17.2/min",
                    "latest_date": "2026-07-03",
                    "category": "breathing",
                    "why_it_matters": "Breathing rate compared with usual can hint recovery strain.",
                    "coaching_use": "Use with sleep, HRV, resting HR, and symptoms.",
                },
            ],
        },
        "data_used": {"days_compared": 4},
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 8,
            "last_sync": "2026-07-03T11:52:00+00:00",
        },
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
                "reason": "Daily HRV helps spot recovery changes versus your usual.",
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
        "data_freshness": {
            "freshness_level": "fresh",
            "freshness_label": "fresh <15 min",
            "latest_observed_date": "2026-07-03",
            "sync_age_minutes": 6,
            "last_sync": "2026-07-03T11:54:00+00:00",
        },
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
