WIDGET_URI = "ui://mehair/today-v2.html"
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
        color: #171a1f;
        background: #f7f8f6;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
      }

      * { box-sizing: border-box; }

      html, body {
        margin: 0;
        min-height: 100%;
      }

      body {
        padding: 12px;
        background: #f7f8f6;
      }

      main {
        max-width: 600px;
        margin: 0 auto;
      }

      .panel {
        --accent: #4f7f36;
        border: 1px solid #dfe4dd;
        border-radius: 8px;
        background: #fff;
        box-shadow: 0 1px 0 rgba(16, 24, 40, 0.04);
        overflow: hidden;
      }

      .topbar {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        padding: 14px 14px 0;
      }

      h1 {
        margin: 0;
        font-size: 15px;
        line-height: 1.2;
        font-weight: 760;
      }

      .date {
        color: #69737a;
        font-size: 12px;
        line-height: 1.25;
        text-align: right;
      }

      .pill {
        display: inline-flex;
        align-items: center;
        min-height: 24px;
        border: 1px solid color-mix(in srgb, var(--accent) 34%, #dfe4dd);
        border-radius: 999px;
        padding: 3px 9px;
        background: color-mix(in srgb, var(--accent) 10%, #fff);
        color: #2d333b;
        font-size: 12px;
        font-weight: 700;
        text-transform: capitalize;
      }

      .hero {
        display: grid;
        grid-template-columns: 126px 1fr;
        gap: 14px;
        align-items: stretch;
        padding: 14px;
      }

      .primary {
        min-height: 118px;
        border: 1px solid color-mix(in srgb, var(--accent) 28%, #e5e7e2);
        border-left: 5px solid var(--accent);
        border-radius: 8px;
        background: color-mix(in srgb, var(--accent) 8%, #fff);
        padding: 12px;
        display: flex;
        flex-direction: column;
        justify-content: center;
      }

      .primary b {
        display: block;
        font-size: 32px;
        line-height: 1;
        font-weight: 820;
      }

      .primary small {
        display: block;
        margin-top: 4px;
        color: #5f6870;
        font-size: 12px;
      }

      .summary {
        min-width: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
      }

      .headline {
        margin: 8px 0 0;
        color: #27313a;
        font-size: 14px;
        line-height: 1.38;
      }

      .source {
        margin-top: 8px;
        color: #69737a;
        font-size: 12px;
        line-height: 1.35;
      }

      .metrics {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        padding: 0 14px 14px;
      }

      .metric {
        min-height: 74px;
        border: 1px solid #e5e7e2;
        border-radius: 8px;
        padding: 10px;
        background: #fbfcfb;
      }

      .metric b {
        display: block;
        overflow-wrap: anywhere;
        color: #20272e;
        font-size: 18px;
        line-height: 1.12;
      }

      .metric span {
        display: block;
        margin-top: 4px;
        color: #667078;
        font-size: 12px;
        line-height: 1.25;
      }

      .metric small {
        display: block;
        margin-top: 4px;
        color: #8a939b;
        font-size: 11px;
        line-height: 1.25;
      }

      .evidence-wrap {
        border-top: 1px solid #edf0ea;
        padding: 12px 14px 14px;
        background: #fcfdfb;
      }

      .section-title {
        margin: 0 0 8px;
        color: #5d6670;
        font-size: 12px;
        font-weight: 760;
      }

      .evidence {
        display: grid;
        gap: 8px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .evidence li {
        border-left: 3px solid var(--accent);
        padding-left: 9px;
        color: #343b43;
        font-size: 13px;
        line-height: 1.35;
      }

      .empty {
        padding: 16px;
        color: #57606a;
        line-height: 1.4;
        font-size: 14px;
      }

      @media (max-width: 480px) {
        body { padding: 10px; }
        .topbar { flex-direction: column; }
        .date { text-align: left; }
        .hero { grid-template-columns: 1fr; }
        .primary { min-height: 98px; }
        .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }

      @media (max-width: 340px) {
        .metrics { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="panel" id="root">
        <div class="empty">Waiting for health context.</div>
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
            appInfo: { name: "mehair-coach-widget", version: "0.2.0" },
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
          root.innerHTML = `<div class="empty">${escapeHtml(data.message || "No synced data yet.")}</div>`;
          return;
        }
        renderModel(toViewModel(data));
      }

      function toViewModel(data) {
        if (data?.latest && Array.isArray(data.days) && (data.latest.stages_minutes || data.latest.sessions_count != null)) {
          return sleepModel(data);
        }
        if (data?.totals && data?.highest_load_day && Array.isArray(data.days)) {
          return activityModel(data);
        }
        if (data?.summary && Array.isArray(data.days) && ("average_hrv_ms" in data.summary || "average_resting_bpm" in data.summary)) {
          return heartModel(data);
        }
        if (data?.metrics && data?.requested_metrics) {
          return metricQueryModel(data);
        }
        return readinessModel(data);
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
          ? `Activity from ${activityDate}; recovery from ${recoveryDate}.`
          : activityDate ? `Using health context from ${activityDate}.` : "Waiting for synced health context.";
        return {
          type: "readiness",
          accent: readinessAccent(label),
          title: "Mehair Coach",
          date: activityDate || data.latest_observed_date || "",
          pill: label,
          primaryValue: `${Math.round(score)}`,
          primaryLabel: "Readiness",
          headline: readiness.recommendation || data.recommendation || "Health context synced.",
          source,
          metrics: [
            ["Steps", intText(today.steps ?? 0)],
            ["Zone minutes", intText(today.active_zone_minutes ?? 0), latestLoad.date && latestLoad.date !== activityDate ? `Latest ${latestLoad.active_zone_minutes ?? 0} on ${latestLoad.date}` : ""],
            ["Active minutes", optionalInt(today.active_minutes)],
            ["Sleep", sleepHours ? `${num(sleepHours, 1)}h` : null, sleep.sessions_count ? `${sleep.sessions_count} sessions` : ""],
            ["Resting HR", today.resting_heart_rate ? `${today.resting_heart_rate} bpm` : heart.avg_bpm ? `${heart.avg_bpm} avg bpm` : null],
            ["HRV", today.hrv_ms ? `${num(today.hrv_ms, 1)} ms` : null],
          ],
          evidence: readiness.evidence || data.evidence || [],
        };
      }

      function sleepModel(data) {
        const latest = data.latest || {};
        const stages = latest.stages_minutes || {};
        const asleep = latest.asleep_hours ?? latest.duration_hours;
        const sessions = latest.sessions_count || 1;
        const delta = data.summary?.latest_vs_average_hours;
        const evidence = [];
        if (delta != null) {
          evidence.push(`Latest sleep is ${Math.abs(delta)}h ${delta < 0 ? "below" : "above"} recent average.`);
        }
        if (latest.awake_minutes != null) {
          evidence.push(`${latest.awake_minutes} minutes awake during the sleep window.`);
        }
        if (stages.deep != null || stages.rem != null) {
          evidence.push(`Deep ${num(stages.deep, 0)}m and REM ${num(stages.rem, 0)}m were detected.`);
        }
        return {
          type: "sleep",
          accent: "#2f6f8f",
          title: "Sleep",
          date: latest.date || "",
          pill: `${sessions} session${sessions === 1 ? "" : "s"}`,
          primaryValue: asleep ? `${num(asleep, 1)}h` : "No data",
          primaryLabel: "Asleep",
          headline: sessions > 1 ? "Split sleep was combined for coaching." : "Sleep session captured.",
          source: latest.date ? `Latest sleep from ${latest.date}.` : "Latest synced sleep.",
          metrics: [
            ["Duration", latest.duration_hours ? `${num(latest.duration_hours, 1)}h` : null],
            ["Awake", latest.awake_minutes != null ? `${latest.awake_minutes}m` : null],
            ["Deep", stages.deep != null ? `${num(stages.deep, 0)}m` : null],
            ["REM", stages.rem != null ? `${num(stages.rem, 0)}m` : null],
            ["Light", stages.light != null ? `${num(stages.light, 0)}m` : null],
            ["Average", data.summary?.average_asleep_hours ? `${num(data.summary.average_asleep_hours, 1)}h` : null],
          ],
          evidence,
        };
      }

      function activityModel(data) {
        const totals = data.totals || {};
        const highest = data.highest_load_day || {};
        const days = data.days || [];
        return {
          type: "activity",
          accent: "#7a6a18",
          title: "Activity Load",
          date: rangeText(days),
          pill: `${days.length || 0} days`,
          primaryValue: intText(totals.active_zone_minutes ?? highest.active_zone_minutes ?? 0),
          primaryLabel: "Zone minutes",
          headline: `${intText(totals.steps ?? 0)} steps across the queried window.`,
          source: highest.date ? `Highest load day: ${highest.date}.` : "Latest synced activity.",
          metrics: [
            ["Steps", intText(totals.steps ?? 0)],
            ["Active minutes", intText(totals.active_minutes ?? 0)],
            ["Zone minutes", intText(totals.active_zone_minutes ?? 0)],
            ["Highest AZM", highest.active_zone_minutes != null ? intText(highest.active_zone_minutes) : null, highest.date || ""],
            ["Latest day", days.length ? days[days.length - 1].date : null],
            ["Distance", sumDistance(days)],
          ],
          evidence: highest.date ? [`${highest.date} had the highest zone-minute load in this window.`] : [],
        };
      }

      function heartModel(data) {
        const days = data.days || [];
        const latest = data.latest || days[days.length - 1] || {};
        const summary = data.summary || {};
        const primary = latest.hrv_ms != null
          ? [`${num(latest.hrv_ms, 1)}`, "Latest HRV"]
          : latest.resting_bpm != null ? [`${latest.resting_bpm}`, "Resting HR"] : ["No data", "Heart"];
        return {
          type: "heart",
          accent: "#8a4b3e",
          title: "Heart Trends",
          date: latest.date || rangeText(days),
          pill: "heart",
          primaryValue: primary[0],
          primaryLabel: primary[1],
          headline: "Recent HRV and resting heart-rate context.",
          source: latest.date ? `Latest heart signals from ${latest.date}.` : "Latest synced heart signals.",
          metrics: [
            ["Latest HRV", latest.hrv_ms != null ? `${num(latest.hrv_ms, 1)} ms` : null],
            ["Avg HRV", summary.average_hrv_ms != null ? `${num(summary.average_hrv_ms, 1)} ms` : null],
            ["Resting HR", latest.resting_bpm != null ? `${latest.resting_bpm} bpm` : null],
            ["Avg resting HR", summary.average_resting_bpm != null ? `${num(summary.average_resting_bpm, 1)} bpm` : null],
            ["Avg BPM", latest.avg_bpm != null ? `${num(latest.avg_bpm, 1)} bpm` : null],
            ["Days", intText(days.length || 0)],
          ],
          evidence: [
            summary.average_hrv_ms != null ? `Average HRV is ${num(summary.average_hrv_ms, 1)} ms.` : null,
            summary.average_resting_bpm != null ? `Average resting HR is ${num(summary.average_resting_bpm, 1)} bpm.` : null,
          ].filter(Boolean),
        };
      }

      function metricQueryModel(data) {
        const metrics = data.metrics || {};
        const entries = Object.entries(metrics);
        return {
          type: "metrics",
          accent: "#4b6f8f",
          title: "Metric Query",
          date: data.start_date && data.end_date ? `${data.start_date} to ${data.end_date}` : "",
          pill: `${data.requested_metrics.length} metrics`,
          primaryValue: intText(data.record_count ?? 0),
          primaryLabel: "Records",
          headline: "Synced local health metrics returned for this window.",
          source: data.source || "local synced store",
          metrics: entries.slice(0, 6).map(([id, item]) => [
            item.catalog?.label || id,
            intText(item.record_count ?? 0),
            item.latest_observed_date || "",
          ]),
          evidence: [
            data.missing_metrics?.length ? `No records in range for: ${data.missing_metrics.join(", ")}.` : null,
            data.unknown_metrics?.length ? `Unsupported metrics ignored: ${data.unknown_metrics.join(", ")}.` : null,
          ].filter(Boolean),
        };
      }

      function renderModel(model) {
        root.style.setProperty("--accent", model.accent || "#4f7f36");
        root.innerHTML = `
          <div class="topbar">
            <div>
              <h1>${escapeHtml(model.title || "Mehair Coach")}</h1>
              <p class="headline">${escapeHtml(model.headline || "Health context synced.")}</p>
            </div>
            <div class="date">${escapeHtml(model.date || "")}</div>
          </div>
          <div class="hero">
            <div class="primary">
              <b>${escapeHtml(model.primaryValue ?? "No data")}</b>
              <small>${escapeHtml(model.primaryLabel || "")}</small>
            </div>
            <div class="summary">
              <div><span class="pill">${escapeHtml(model.pill || model.type || "health")}</span></div>
              <div class="source">${escapeHtml(model.source || "Latest synced health context.")}</div>
            </div>
          </div>
          <div class="metrics">
            ${(model.metrics || []).slice(0, 6).map((item) => metric(item[0], item[1], item[2])).join("")}
          </div>
          <div class="evidence-wrap">
            <p class="section-title">Why</p>
            <ul class="evidence">
              ${((model.evidence || []).length ? model.evidence : ["More synced Fitbit data will make this richer."]).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            </ul>
          </div>
        `;
      }

      function metric(label, value, detail) {
        const detailHtml = detail ? `<small>${escapeHtml(detail)}</small>` : "";
        return `<div class="metric"><b>${escapeHtml(value ?? "No data")}</b><span>${escapeHtml(label)}</span>${detailHtml}</div>`;
      }

      function readinessAccent(label) {
        if (label === "green") return "#4f7f36";
        if (label === "yellow") return "#9b741c";
        if (label === "red") return "#a94f43";
        return "#667078";
      }

      function finiteNumber(value, fallback) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
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
