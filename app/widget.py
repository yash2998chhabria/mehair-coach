WIDGET_URI = "ui://mehair/today-v1.html"
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
        padding: 14px;
        background: #f7f8f6;
      }

      main {
        display: grid;
        gap: 12px;
        max-width: 560px;
        margin: 0 auto;
      }

      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }

      h1 {
        margin: 0;
        font-size: 17px;
        line-height: 1.2;
        font-weight: 720;
      }

      .date {
        color: #667085;
        font-size: 12px;
        white-space: nowrap;
      }

      .panel {
        border: 1px solid #dde2dc;
        border-radius: 8px;
        background: #fff;
        padding: 14px;
      }

      .readiness {
        display: grid;
        grid-template-columns: 86px 1fr;
        gap: 14px;
        align-items: center;
      }

      .score {
        width: 76px;
        aspect-ratio: 1;
        display: grid;
        place-items: center;
        border-radius: 50%;
        background: conic-gradient(var(--ring, #7a8f56) calc(var(--score, 0) * 1%), #edf0ec 0);
      }

      .score > span {
        width: 60px;
        aspect-ratio: 1;
        display: grid;
        place-items: center;
        border-radius: 50%;
        background: #fff;
        font-size: 22px;
        font-weight: 760;
      }

      .label {
        width: fit-content;
        border-radius: 999px;
        padding: 4px 9px;
        background: #edf4e3;
        color: #405a22;
        font-size: 12px;
        font-weight: 680;
        text-transform: capitalize;
      }

      .recommendation {
        margin: 8px 0 0;
        color: #2d333b;
        line-height: 1.35;
        font-size: 14px;
      }

      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }

      .metric {
        min-height: 76px;
        border: 1px solid #e5e7e2;
        border-radius: 8px;
        padding: 12px;
        background: #fbfcfb;
      }

      .metric b {
        display: block;
        font-size: 18px;
        line-height: 1.15;
      }

      .metric span {
        display: block;
        margin-top: 4px;
        color: #687076;
        font-size: 12px;
      }

      .evidence {
        display: grid;
        gap: 8px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .evidence li {
        border-left: 3px solid #9eb36f;
        padding-left: 9px;
        color: #363b42;
        font-size: 13px;
        line-height: 1.35;
      }

      .empty {
        color: #57606a;
        line-height: 1.4;
        font-size: 14px;
      }

      @media (max-width: 420px) {
        body { padding: 10px; }
        .readiness { grid-template-columns: 1fr; }
        .grid { grid-template-columns: 1fr; }
        header { align-items: flex-start; flex-direction: column; }
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Mehair Coach</h1>
        <div class="date" id="date"></div>
      </header>
      <section class="panel" id="root">
        <div class="empty">Waiting for health context.</div>
      </section>
    </main>
    <script>
      const root = document.getElementById("root");
      const dateEl = document.getElementById("date");

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
            appInfo: { name: "mehair-coach-widget", version: "0.1.0" },
            appCapabilities: {},
            protocolVersion: "2026-01-26",
          });
          rpcNotify("ui/notifications/initialized", {});
        } catch (error) {
          console.error(error);
        }
      }

      function metric(label, value) {
        return `<div class="metric"><b>${escapeHtml(value ?? "No data")}</b><span>${escapeHtml(label)}</span></div>`;
      }

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }

      function render() {
        const data = state.data || {};
        const status = data.status;
        if (status && status !== "ok" && status !== "connected") {
          root.innerHTML = `<div class="empty">${escapeHtml(data.message || "No synced data yet.")}</div>`;
          dateEl.textContent = "";
          return;
        }

        const context = data.today ? data : data.context || data;
        const readiness = data.readiness || context.readiness || {};
        const today = context.today || {};
        const sleep = today.sleep || {};
        const heart = today.heart || {};
        const label = readiness.label || "pending";
        const score = Number.isFinite(Number(readiness.score)) ? Number(readiness.score) : 0;
        const color = label === "green" ? "#79a64b" : label === "yellow" ? "#c59b3a" : label === "red" ? "#c75f4c" : "#8d99a6";
        root.style.setProperty("--score", score);
        root.style.setProperty("--ring", color);
        dateEl.textContent = context.latest_date || data.latest_observed_date || "";

        const evidence = readiness.evidence || data.evidence || [];
        root.innerHTML = `
          <div class="readiness">
            <div class="score"><span>${Math.round(score)}</span></div>
            <div>
              <div class="label">${escapeHtml(label)}</div>
              <p class="recommendation">${escapeHtml(readiness.recommendation || data.recommendation || "Health context synced.")}</p>
            </div>
          </div>
          <div class="grid" style="margin-top: 12px">
            ${metric("Steps", today.steps)}
            ${metric("Zone minutes", today.active_zone_minutes)}
            ${metric("Sleep", sleep.duration_hours ? `${sleep.duration_hours}h` : null)}
            ${metric("Resting heart rate", today.resting_heart_rate ? `${today.resting_heart_rate} bpm` : heart.avg_bpm ? `${heart.avg_bpm} avg bpm` : null)}
          </div>
          <ul class="evidence" style="margin-top: 12px">
            ${(evidence.length ? evidence : ["More synced Fitbit data will make this richer."]).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>
        `;
      }

      render();
      initialize();
    </script>
  </body>
</html>
""".strip()
