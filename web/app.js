"use strict";
(function () {
  // Same order as Excel's default chart palette used by report.py.
  var PALETTE = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47", "#9E480E", "#997300"];
  var STATE_MS = 1500;
  var TIMELINE_MS = 3000;
  var SUMMARY_MS = 5000;
  var MAX_POINTS = 1500;
  var nf = new Intl.NumberFormat("id-ID");

  var state = null;
  var colors = {};
  var activeTab = null;
  var chart = null;
  var points = [];
  var nextSeq = 0;
  var lastSources = "";

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fmt(n) { return n === null || n === undefined ? "--" : nf.format(n); }

  function api(path, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    opts.cache = "no-store";
    return fetch(path, opts).then(function (res) {
      if (res.status === 403) {
        setConn("Sesi tidak valid. Scan ulang QR dari PeakView.", true);
        throw new Error("forbidden");
      }
      return res;
    });
  }

  function getJson(path) {
    return api(path).then(function (res) {
      if (!res.ok) throw new Error("http " + res.status);
      return res.json();
    });
  }

  function setConn(text, bad) {
    var node = $("conn");
    node.textContent = text;
    node.classList.toggle("bad", !!bad);
  }

  function toast(text, isErr) {
    var node = $("toast");
    node.textContent = text;
    node.classList.toggle("err", !!isErr);
  }

  // ---------- tabs ----------
  function showTab(name) {
    activeTab = name;
    ["control", "dashboard"].forEach(function (t) {
      $("tab-" + t).hidden = t !== name;
    });
    document.querySelectorAll(".tab").forEach(function (b) {
      b.setAttribute("aria-selected", String(b.dataset.tab === name));
    });
    if (name === "dashboard") {
      ensureChart();
      pollTimeline();
      pollSummary();
    }
  }

  function defaultTab() {
    var phone = window.matchMedia("(max-width: 800px)").matches ||
      window.matchMedia("(pointer: coarse)").matches;
    return phone ? "control" : "dashboard";
  }

  // ---------- state rendering ----------
  function assignColors(sources) {
    sources.forEach(function (s, i) { colors[s] = PALETTE[i % PALETTE.length]; });
  }

  function renderState(s) {
    state = s;
    if (lastSources !== s.sources.join("|")) {
      lastSources = s.sources.join("|");
      assignColors(s.sources);
      resetChart();
    }
    var runDot = $("run-dot");
    runDot.className = "dot " + (s.running ? "ok" : "error");
    runDot.title = s.running ? "Capture berjalan" : "Capture berhenti";

    $("now-name").textContent = s.segment || "-";
    $("now-pos").textContent = (s.index + 1) + " / " + s.total;
    var group = s.segments[s.index] ? s.segments[s.index].group : "-";
    $("now-group").textContent = group;
    $("btn-prev").disabled = s.index <= 0;
    $("btn-next").disabled = s.index >= s.total - 1;
    $("dash-segment").textContent = s.segment || "-";

    renderViewers(s);
    renderSegments(s);
    renderCards(s);
  }

  function healthDot(status) {
    var d = el("span", "dot " + (status === "ok" ? "ok" : status === "warn" ? "warn" : "error"));
    d.title = status === "ok" ? "OCR normal" : status === "warn" ? "OCR ragu" : "OCR tidak terbaca";
    return d;
  }

  function renderViewers(s) {
    var list = $("viewer-list");
    list.replaceChildren();
    s.sources.forEach(function (src) {
      var li = el("li");
      var sw = el("span", "swatch");
      sw.style.setProperty("--c", colors[src]);
      var name = el("span", "v-name", src);
      name.appendChild(el("small", "num", "peak segmen: " + fmt(s.peaks[src])));
      li.append(sw, name, el("span", "v-val num", fmt(s.viewers[src])), healthDot(s.health[src]));
      list.appendChild(li);
    });
  }

  function renderSegments(s) {
    var key = s.segments.map(function (x) { return x.name; }).join("\n") + "\n#" + s.index;
    var host = $("segment-groups");
    if (host.dataset.key === key) return;
    host.dataset.key = key;
    host.replaceChildren();
    var order = [];
    var byGroup = {};
    s.segments.forEach(function (seg, i) {
      if (!byGroup[seg.group]) { byGroup[seg.group] = []; order.push(seg.group); }
      byGroup[seg.group].push({ name: seg.name, index: i });
    });
    order.forEach(function (g) {
      var wrap = el("div", "group");
      wrap.appendChild(el("h3", "group-title", g));
      var grid = el("div", "seg-grid");
      byGroup[g].forEach(function (item) {
        var b = el("button", "seg" + (item.index === s.index ? " active" : ""), item.name);
        b.type = "button";
        b.addEventListener("click", function () { postSegment({ name: item.name }); });
        grid.appendChild(b);
      });
      wrap.appendChild(grid);
      host.appendChild(wrap);
    });
  }

  function renderCards(s) {
    var host = $("cards");
    host.replaceChildren();
    s.sources.forEach(function (src) {
      var card = el("div", "card");
      card.style.setProperty("--c", colors[src]);
      var top = el("div", "c-top");
      top.append(el("span", "", src), healthDot(s.health[src]));
      card.append(top, el("div", "c-val num", fmt(s.viewers[src])),
        el("div", "c-peak num", "peak segmen: " + fmt(s.peaks[src])));
      host.appendChild(card);
    });
  }

  // ---------- actions ----------
  function postSegment(body) {
    toast("");
    api("/api/segment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (res) {
      if (!res.ok) throw new Error("http " + res.status);
      return res.json();
    }).then(function (data) {
      renderState(data.state);
    }).catch(function (err) {
      if (err.message !== "forbidden") toast("Gagal ganti segmen", true);
    });
  }

  function downloadReport() {
    var btn = $("btn-report");
    btn.disabled = true;
    api("/api/report.xlsx").then(function (res) {
      if (res.status === 409) { alert("Belum ada data peak untuk di-report."); return null; }
      if (!res.ok) throw new Error("http " + res.status);
      var disposition = res.headers.get("Content-Disposition") || "";
      var m = /filename="([^"]+)"/.exec(disposition);
      return res.blob().then(function (blob) { return { blob: blob, name: m ? m[1] : "laporan_peak.xlsx" }; });
    }).then(function (file) {
      if (!file) return;
      var url = URL.createObjectURL(file.blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }).catch(function (err) {
      if (err.message !== "forbidden") alert("Report gagal dibuat.");
    }).then(function () { btn.disabled = false; });
  }

  // ---------- chart ----------
  var segmentMarkers = {
    id: "segmentMarkers",
    afterDatasetsDraw: function (c) {
      var ctx = c.ctx;
      var area = c.chartArea;
      var x = c.scales.x;
      ctx.save();
      ctx.strokeStyle = "rgba(255,176,32,.55)";
      ctx.fillStyle = "rgba(255,176,32,.9)";
      ctx.font = "11px system-ui, sans-serif";
      ctx.setLineDash([4, 4]);
      for (var i = 1; i < points.length; i++) {
        if (points[i].segment === points[i - 1].segment) continue;
        var px = x.getPixelForValue(i);
        if (px < area.left || px > area.right) continue;
        ctx.beginPath();
        ctx.moveTo(px, area.top);
        ctx.lineTo(px, area.bottom);
        ctx.stroke();
        ctx.save();
        ctx.translate(px + 3, area.top + 4);
        ctx.rotate(Math.PI / 2);
        ctx.setLineDash([]);
        ctx.fillText(points[i].segment, 0, 0);
        ctx.restore();
      }
      ctx.restore();
    }
  };

  function ensureChart() {
    if (chart || !state || typeof Chart === "undefined") return;
    chart = new Chart($("chart"), {
      type: "line",
      data: { labels: [], datasets: [] },
      options: {
        animation: false,
        maintainAspectRatio: false,
        spanGaps: false,
        interaction: { mode: "index", intersect: false },
        elements: { point: { radius: 0 }, line: { borderWidth: 2, tension: 0.15 } },
        plugins: { legend: { labels: { color: "#e8edf2" } } },
        scales: {
          x: { ticks: { color: "#8b9aa9", maxTicksLimit: 8, autoSkip: true }, grid: { color: "#2d3a47" } },
          y: { ticks: { color: "#8b9aa9", callback: function (v) { return nf.format(v); } },
               grid: { color: "#2d3a47" } }
        }
      },
      plugins: [segmentMarkers]
    });
    resetChart();
  }

  function resetChart() {
    points = [];
    nextSeq = 0;
    if (!chart || !state) return;
    chart.data.labels = [];
    chart.data.datasets = state.sources.map(function (src) {
      return { label: src, data: [], borderColor: colors[src], backgroundColor: colors[src] };
    });
    chart.update("none");
  }

  function clock(epoch) {
    var d = new Date(epoch * 1000);
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function applyTimeline(data) {
    if (!chart || !state) return;
    nextSeq = data.next;
    if (!data.points.length) return;
    points = points.concat(data.points);
    if (points.length > MAX_POINTS) points = points.slice(points.length - MAX_POINTS);
    chart.data.labels = points.map(function (p) { return clock(p.t); });
    chart.data.datasets.forEach(function (ds) {
      ds.data = points.map(function (p) {
        var v = p.values[ds.label];
        return v === undefined ? null : v;
      });
    });
    chart.update("none");
  }

  function renderSummary(data) {
    var table = $("summary");
    table.replaceChildren();
    var head = el("tr");
    head.appendChild(el("th", "", "Segmen"));
    data.sources.forEach(function (s) { head.appendChild(el("th", "", s)); });
    head.appendChild(el("th", "", "Total"));
    var thead = el("thead");
    thead.appendChild(head);
    var tbody = el("tbody");
    data.segments.forEach(function (row) {
      var tr = el("tr", state && row.name === state.segment ? "current" : "");
      tr.appendChild(el("td", "", row.name));
      data.sources.forEach(function (s) { tr.appendChild(el("td", "num", fmt(row.peaks[s]))); });
      tr.appendChild(el("td", "num", fmt(row.total)));
      tbody.appendChild(tr);
    });
    if (!data.segments.length) {
      var empty = el("tr");
      var td = el("td", "", "Belum ada data peak");
      td.colSpan = data.sources.length + 2;
      empty.appendChild(td);
      tbody.appendChild(empty);
    }
    table.append(thead, tbody);
  }

  // ---------- polling ----------
  function pollState() {
    return getJson("/api/state").then(function (s) {
      renderState(s);
      setConn("terhubung", false);
    }).catch(function (err) {
      if (err.message !== "forbidden") setConn("koneksi terputus, mencoba lagi…", true);
    });
  }

  function pollTimeline() {
    if (activeTab !== "dashboard" || !chart) return;
    getJson("/api/timeline?since=" + nextSeq).then(applyTimeline).catch(function () {});
  }

  function pollSummary() {
    if (activeTab !== "dashboard") return;
    getJson("/api/summary").then(renderSummary).catch(function () {});
  }

  function every(ms, fn) {
    setInterval(function () { if (!document.hidden) fn(); }, ms);
  }

  function init() {
    document.querySelectorAll(".tab").forEach(function (b) {
      b.addEventListener("click", function () { showTab(b.dataset.tab); });
    });
    $("btn-prev").addEventListener("click", function () { postSegment({ action: "prev" }); });
    $("btn-next").addEventListener("click", function () { postSegment({ action: "next" }); });
    $("btn-report").addEventListener("click", downloadReport);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) pollState(); });

    pollState().then(function () { showTab(defaultTab()); });
    every(STATE_MS, pollState);
    every(TIMELINE_MS, pollTimeline);
    every(SUMMARY_MS, pollSummary);
  }

  init();
})();
