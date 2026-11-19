(() => {
  "use strict";

  function preventZoom(event) {
    event.preventDefault();
  }
  for (const type of ["gesturestart", "gesturechange", "gestureend"]) {
    document.addEventListener(type, preventZoom, { passive: false });
  }
  document.addEventListener("touchmove", (event) => {
    if (typeof event.scale === "number" && event.scale !== 1) {
      event.preventDefault();
    }
  }, { passive: false });

  const POLL_MS = 45_000;
  const DATA_BRANCH_URL =
    "https://raw.githubusercontent.com/RILAKKUMA-KUKI/predict/data/quotes.json";

  const tabsEl = document.getElementById("tabs");
  const filterEl = document.getElementById("filter");
  const sortEl = document.getElementById("sort");
  const quotesBody = document.querySelector("#quotes-table tbody");
  const outlookBody = document.querySelector("#outlook-table tbody");
  const emptyEl = document.getElementById("quotes-empty");
  const pollEl = document.getElementById("poll-status");
  const sourceLine = document.getElementById("source-line");
  const chartSymbolEl = document.getElementById("chart-symbol");
  const chartBox = document.getElementById("chart-box");
  const chartNote = document.getElementById("chart-note");
  const periodTabs = document.getElementById("period-tabs");

  let data = null;
  let lastGoodData = null;
  let activeTab = "all";
  let sortKey = "default";
  let headerSort = null;
  let selectedCode = "US.VOO";
  let period = "daily";
  let pollTimer = null;
  let lastPollOkAt = null;

  const $ = (id) => document.getElementById(id);

  function dataUrls() {
    const t = Date.now();
    return [
      `${DATA_BRANCH_URL}?t=${t}`,
      `./quotes.json?t=${t}`,
    ];
  }

  async function fetchQuotes() {
    let lastErr = null;
    for (const url of dataUrls()) {
      try {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) {
          lastErr = new Error(`${url} HTTP ${resp.status}`);
          continue;
        }
        const json = await resp.json();
        if (!json || !Array.isArray(json.quotes)) {
          lastErr = new Error("數據格式不正確");
          continue;
        }
        return json;
      } catch (err) {
        lastErr = err;
      }
    }
    throw lastErr || new Error("未能讀取報價");
  }

  function hktSuffix(text) {
    if (!text) return "—";
    if (String(text).includes("香港時間")) return String(text);
    return `${text}（香港時間）`;
  }

  function fmtPx(value, unit) {
    if (value == null || Number.isNaN(value)) return "—";
    const abs = Math.abs(value);
    const digits = unit === "POINT" ? 2 : abs < 10 ? 3 : 2;
    const body = value.toLocaleString("zh-HK", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    return unit === "POINT" ? `${body} 點` : body;
  }

  function fmtSigned(value, unit, asPct) {
    if (value == null || Number.isNaN(value)) return { text: "—", cls: "" };
    const digits = asPct ? 2 : unit === "POINT" || Math.abs(value) >= 10 ? 2 : 3;
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    const body = `${sign}${Math.abs(value).toLocaleString("zh-HK", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}`;
    const text = asPct ? `${body}%` : unit === "POINT" ? `${body} 點` : body;
    const cls = value > 0 ? "up" : value < 0 ? "down" : "";
    return { text, cls };
  }

  function fmtVol(value) {
    if (value == null) return "—";
    if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)} 億`;
    if (value >= 10_000) return `${(value / 10_000).toFixed(1)} 萬`;
    return value.toLocaleString("zh-HK");
  }

  function levelText(level, unit) {
    if (!level) return "—";
    if (level.value != null) {
      const note = level.note ? `（${level.note}）` : "";
      return `${fmtPx(level.value, unit)}${note}`;
    }
    return level.note || "—";
  }

  function sparkline(points, up) {
    if (!points || points.length < 2) return "";
    const vals = points.map((p) => p.close).filter((v) => typeof v === "number");
    if (vals.length < 2) return "";
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;
    const w = 84;
    const h = 28;
    const pad = 2;
    const coords = vals.map((v, i) => {
      const x = pad + (i * (w - pad * 2)) / (vals.length - 1);
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const color = up ? "#3ecf8e" : "#ee6d76";
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="1.6" points="${coords.join(" ")}"/></svg>`;
  }

  function visibleRows() {
    if (!data) return [];
    const needle = filterEl.value.trim().toLowerCase();
    let rows = data.quotes.filter((row) => activeTab === "all" || row.tab === activeTab);
    if (needle) {
      rows = rows.filter((row) =>
        row.code.toLowerCase().includes(needle) ||
        (row.name || "").toLowerCase().includes(needle)
      );
    }
    const key = headerSort || sortKey;
    if (key === "default" || !key) return rows;
    const copy = rows.slice();
    copy.sort((a, b) => {
      const fail = (row) => (row.status === "ok" || row.status === "stale" ? 0 : 1);
      if (fail(a) !== fail(b)) return fail(a) - fail(b);
      if (key === "pctDesc") return (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity);
      if (key === "pctAsc") return (a.changePct ?? Infinity) - (b.changePct ?? Infinity);
      if (key === "nearHigh") return (b.distHighPct ?? -Infinity) - (a.distHighPct ?? -Infinity);
      if (key === "farHigh") return (a.distHighPct ?? Infinity) - (b.distHighPct ?? Infinity);
      if (key === "posHigh") return (b.pos52Pct ?? -Infinity) - (a.pos52Pct ?? -Infinity);
      if (key === "code") return a.code.localeCompare(b.code);
      if (key === "name") return (a.name || "").localeCompare(b.name || "", "zh-Hant");
      if (key === "last") return (b.last ?? -Infinity) - (a.last ?? -Infinity);
      if (key === "change") return (b.change ?? -Infinity) - (a.change ?? -Infinity);
      if (key === "changePct") return (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity);
      if (key === "pos52Pct") return (b.pos52Pct ?? -Infinity) - (a.pos52Pct ?? -Infinity);
      return 0;
    });
    return copy;
  }

  function extCell(row) {
    if (row.prePrice != null) {
      const pct = fmtSigned(row.preChangePct, row.unit, true);
      return `<span class="${pct.cls}">${fmtPx(row.prePrice, row.unit)} ${pct.text}</span>`;
    }
    if (row.postPrice != null) {
      const pct = fmtSigned(row.postChangePct, row.unit, true);
      return `<span class="${pct.cls}">${fmtPx(row.postPrice, row.unit)} ${pct.text}</span>`;
    }
    return "—";
  }

  function statusBadge(row) {
    if (row.status === "error") return `<span class="badge badge-fail">未能取得</span>`;
    if (row.status === "stale") return `<span class="badge badge-fail">過時</span>`;
    return "";
  }

  function biasBadge(bias) {
    if (bias === "偏多") return `<span class="badge badge-up">偏多</span>`;
    if (bias === "偏空") return `<span class="badge badge-down">偏空</span>`;
    if (bias === "觀望") return `<span class="badge badge-watch">觀望</span>`;
    return "—";
  }

  function prevByCode() {
    const map = new Map();
    if (lastGoodData && lastGoodData.quotes) {
      for (const row of lastGoodData.quotes) map.set(row.code, row);
    }
    return map;
  }

  function changed(prev, row, field) {
    if (!prev) return false;
    return prev[field] !== row[field];
  }

  function renderQuotes() {
    const rows = visibleRows();
    emptyEl.classList.toggle("hidden", rows.length > 0);
    const prevMap = prevByCode();
    quotesBody.innerHTML = rows.map((row) => {
      const failed = row.status === "error" && row.last == null;
      const chg = fmtSigned(row.change, row.unit, false);
      const pct = fmtSigned(row.changePct, row.unit, true);
      const hist = row.historyDaily || [];
      const sparkUp = hist.length >= 2 ? hist[hist.length - 1].close >= hist[0].close : (row.changePct ?? 0) >= 0;
      const prev = prevMap.get(row.code);
      const flash = (field) => (changed(prev, row, field) ? " flash" : "");
      const selected = row.code === selectedCode ? " is-selected" : "";
      const pos = row.pos52Pct == null ? "—" : `${row.pos52Pct.toFixed(1)}%`;
      if (failed) {
        return `<tr data-code="${row.code}" class="${selected}">
          <td class="code">${row.code} ${statusBadge(row)}</td>
          <td class="name">${row.name || ""}</td>
          <td class="num" colspan="10">未能取得公開報價</td>
        </tr>`;
      }
      return `<tr data-code="${row.code}" class="${selected}">
        <td class="code">${row.code} ${statusBadge(row)}</td>
        <td class="name">${row.name || ""}</td>
        <td class="num${flash("last")}">${fmtPx(row.last, row.unit)}</td>
        <td class="num ${chg.cls}${flash("change")}">${chg.text}</td>
        <td class="num ${pct.cls}${flash("changePct")}">${pct.text}</td>
        <td class="num">${fmtPx(row.open, row.unit)}</td>
        <td class="num">${fmtPx(row.high, row.unit)}</td>
        <td class="num">${fmtPx(row.low, row.unit)}</td>
        <td class="num">${fmtVol(row.volume)}</td>
        <td class="num${flash("prePrice")}${flash("postPrice")}">${extCell(row)}</td>
        <td class="num">${pos}</td>
        <td>${sparkline(hist, sparkUp)}</td>
      </tr>`;
    }).join("");

    outlookBody.innerHTML = rows.map((row) => {
      const failed = row.status === "error" && row.last == null;
      const selected = row.code === selectedCode ? " is-selected" : "";
      if (failed) {
        return `<tr data-code="${row.code}" class="${selected}">
          <td class="code">${row.code}</td>
          <td class="name">${row.name || ""}</td>
          <td colspan="6">未能取得，故未有短線看法</td>
        </tr>`;
      }
      return `<tr data-code="${row.code}" class="${selected}">
        <td class="code">${row.code}</td>
        <td class="name">${row.name || ""}</td>
        <td>${biasBadge(row.bias)}</td>
        <td class="view">${row.view || "—"}</td>
        <td class="num">${levelText(row.levels && row.levels.support, row.unit)}</td>
        <td class="num">${levelText(row.levels && row.levels.breakUp, row.unit)}</td>
        <td>${levelText(row.levels && row.levels.breakDown, row.unit)}</td>
        <td class="weaken">${row.weaken || "—"}</td>
      </tr>`;
    }).join("");
  }

  function fillTimes(doc) {
    $("t-page").textContent = hktSuffix(doc.generatedAtHKT);
    $("t-source").textContent = hktSuffix((doc.source && doc.source.pulledAtHKT) || doc.sourcePulledAtHKT);
    $("t-us-reg").textContent = (doc.sessions && doc.sessions.usRegular && doc.sessions.usRegular.label) || "—";
    $("t-us-ext").textContent = (doc.sessions && doc.sessions.usExtended && doc.sessions.usExtended.label) || "—";
    $("t-hk").textContent = (doc.sessions && doc.sessions.hk && doc.sessions.hk.label) || "—";
    $("t-xau").textContent = (doc.sessions && doc.sessions.xauusd && doc.sessions.xauusd.label) || "—";
    const src = doc.source || {};
    const gold = src.goldSpot ? `黃金現貨：${src.goldSpot}` : "";
    sourceLine.textContent = [
      src.label || "公開市場數據（非富途官方報價）",
      src.pulledAtHKT ? `來源拉取 ${src.pulledAtHKT}（香港時間）` : "",
      gold,
    ].filter(Boolean).join(" · ");
  }

  function fillChartSelect() {
    if (!data) return;
    const current = selectedCode;
    chartSymbolEl.innerHTML = data.quotes.map((row) =>
      `<option value="${row.code}">${row.code} ${row.name}</option>`
    ).join("");
    if (data.quotes.some((row) => row.code === current)) {
      chartSymbolEl.value = current;
    } else {
      selectedCode = "US.VOO";
      chartSymbolEl.value = selectedCode;
    }
  }

  function renderChart() {
    if (!data) return;
    const row = data.quotes.find((item) => item.code === selectedCode) || data.quotes[0];
    if (!row) {
      chartBox.innerHTML = "";
      return;
    }
    const series = period === "weekly" ? row.historyWeekly : row.historyDaily;
    const label = period === "weekly" ? "近 26 週收市價" : "近 60 個交易日收市價";
    chartNote.textContent = `${label}；走勢圖係快照系列，唔係即時跳價。`;
    if (!series || series.length < 2) {
      chartBox.innerHTML = `<p class="section-note">呢隻標的暫時未有足夠走勢快照。</p>`;
      return;
    }
    const vals = series.map((p) => p.close);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const padTop = 16;
    const padBottom = 28;
    const padLeft = 64;
    const padRight = 16;
    const w = 1000;
    const h = 280;
    const span = max - min || 1;
    const x = (i) => padLeft + (i * (w - padLeft - padRight)) / (vals.length - 1);
    const y = (v) => padTop + (1 - (v - min) / span) * (h - padTop - padBottom);
    const points = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const area = `${padLeft},${y(min)} ` + vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ") + ` ${x(vals.length - 1)},${y(min)}`;
    const firstDate = series[0].date.slice(5);
    const lastDate = series[series.length - 1].date.slice(5);
    const midDate = series[Math.floor(series.length / 2)].date.slice(5);
    const ticks = [max, (max + min) / 2, min];
    const grid = ticks.map((tick) => {
      const yy = y(tick);
      return `<line class="chart-grid" x1="${padLeft}" x2="${w - padRight}" y1="${yy}" y2="${yy}"></line>
        <text class="chart-axis" x="${padLeft - 8}" y="${yy + 4}" text-anchor="end">${fmtPx(tick, row.unit)}</text>`;
    }).join("");
    chartBox.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${row.code} 走勢快照">
      <defs>
        <linearGradient id="chartFade" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#cbb07a" stop-opacity="0.28"/>
          <stop offset="100%" stop-color="#cbb07a" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${grid}
      <polygon class="chart-fill" points="${area}"></polygon>
      <polyline class="chart-line" points="${points}"></polyline>
      <text class="chart-axis" x="${padLeft}" y="${h - 8}">${firstDate}</text>
      <text class="chart-axis" x="${(padLeft + w - padRight) / 2}" y="${h - 8}" text-anchor="middle">${midDate}</text>
      <text class="chart-axis" x="${w - padRight}" y="${h - 8}" text-anchor="end">${lastDate}</text>
    </svg>`;
  }

  function updatePollStatus(kind, message) {
    pollEl.classList.remove("is-live", "is-stale", "is-error");
    if (kind) pollEl.classList.add(kind);
    pollEl.textContent = message;
  }

  function applyData(doc, fromPoll) {
    const prev = data;
    lastGoodData = prev || lastGoodData;
    data = doc;
    fillTimes(doc);
    fillChartSelect();
    renderQuotes();
    renderChart();
    lastPollOkAt = doc.generatedAtHKT;
    const failCount = (doc.failures || []).length;
    const failNote = failCount ? `，${failCount} 隻未能更新` : "";
    updatePollStatus(
      "is-live",
      `已自動更新 · ${doc.generatedAtHKT}（香港時間）${failNote} · 約 45 秒後再讀`
    );
    lastGoodData = doc;
  }

  async function poll() {
    try {
      const doc = await fetchQuotes();
      applyData(doc, true);
    } catch (err) {
      if (data) {
        updatePollStatus(
          "is-stale",
          `讀取失敗，仍顯示上次數據 · 上次成功 ${lastPollOkAt || "時間不詳"}（香港時間）`
        );
      } else {
        updatePollStatus("is-error", "未能讀取報價，稍後會再試");
      }
      console.warn(err);
    }
  }

  function selectCode(code) {
    selectedCode = code;
    if (chartSymbolEl.value !== code) chartSymbolEl.value = code;
    renderQuotes();
    renderChart();
  }

  tabsEl.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (!btn) return;
    activeTab = btn.getAttribute("data-tab");
    for (const el of tabsEl.querySelectorAll(".tab")) {
      el.classList.toggle("is-active", el === btn);
      el.setAttribute("aria-selected", el === btn ? "true" : "false");
    }
    renderQuotes();
  });

  periodTabs.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-period]");
    if (!btn) return;
    period = btn.getAttribute("data-period");
    for (const el of periodTabs.querySelectorAll(".tab")) {
      el.classList.toggle("is-active", el === btn);
      el.setAttribute("aria-selected", el === btn ? "true" : "false");
    }
    renderChart();
  });

  filterEl.addEventListener("input", renderQuotes);
  sortEl.addEventListener("change", () => {
    sortKey = sortEl.value;
    headerSort = null;
    renderQuotes();
  });

  document.querySelector("#quotes-table thead").addEventListener("click", (event) => {
    const th = event.target.closest("[data-sort]");
    if (!th) return;
    const key = th.getAttribute("data-sort");
    if (key === "changePct" && (headerSort === "pctDesc" || sortKey === "pctDesc")) {
      headerSort = "pctAsc";
      sortEl.value = "pctAsc";
      sortKey = "pctAsc";
    } else if (key === "changePct") {
      headerSort = "pctDesc";
      sortEl.value = "pctDesc";
      sortKey = "pctDesc";
    } else {
      headerSort = key;
    }
    renderQuotes();
  });

  quotesBody.addEventListener("click", (event) => {
    const tr = event.target.closest("tr[data-code]");
    if (tr) selectCode(tr.getAttribute("data-code"));
  });
  outlookBody.addEventListener("click", (event) => {
    const tr = event.target.closest("tr[data-code]");
    if (tr) selectCode(tr.getAttribute("data-code"));
  });
  chartSymbolEl.addEventListener("change", () => selectCode(chartSymbolEl.value));

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });

  function loop() {
    poll();
    pollTimer = setInterval(poll, POLL_MS);
  }

  loop();
})();
