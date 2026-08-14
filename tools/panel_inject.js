(() => {
  const old = document.getElementById("iptv-debug-panel");
  if (old) old.remove();

  const panel = document.createElement("div");
  panel.id = "iptv-debug-panel";
  panel.style.cssText =
    "position:fixed;right:12px;bottom:12px;z-index:2147483647;width:320px;background:#111;color:#fff;border:3px solid #ffc107;border-radius:10px;padding:12px;font:13px/1.35 Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.55)";

  const title = document.createElement("div");
  title.textContent = "IPTV Debug";
  title.style.cssText = "font-weight:700;color:#ffc107;margin-bottom:8px;font-size:14px";

  const status = document.createElement("div");
  status.id = "iptv-debug-status";
  status.textContent = "Use o botao amarelo para copiar o erro";
  status.style.cssText = "margin-bottom:8px;color:#ffe082";

  function mkBtn(id, label, bg, color) {
    const b = document.createElement("button");
    b.id = id;
    b.type = "button";
    b.textContent = label;
    b.style.cssText =
      "display:block;width:100%;padding:10px;margin:0 0 8px 0;border:0;border-radius:8px;background:" +
      bg +
      ";color:" +
      color +
      ";font-weight:700;cursor:pointer;font-size:13px";
    return b;
  }

  const copyBtn = mkBtn("iptv-copy-error-logs-btn", "COPY ERROR LOGS", "#ffc107", "#111");
  const globoBtn = mkBtn("iptv-play-globo-rj", "Play TV Globo RJ (MPV)", "#2e7d32", "#fff");
  const mpvBtn = mkBtn("iptv-open-mpv-btn", "Open current in MPV", "#333", "#fff");
  const vlcBtn = mkBtn("iptv-open-vlc-btn", "Open current in VLC", "#333", "#fff");

  window.__iptvErrorLogBuffer = window.__iptvErrorLogBuffer || [];
  if (!window.__iptvConsoleHooked) {
    window.__iptvConsoleHooked = true;
    ["error", "warn", "info", "log"].forEach((level) => {
      const orig = console[level].bind(console);
      console[level] = (...args) => {
        try {
          const msg = args
            .map((a) => (a instanceof Error ? a.stack || a.message : String(a)))
            .join(" ");
          window.__iptvErrorLogBuffer.push({
            ts: new Date().toISOString(),
            level,
            message: msg,
          });
        } catch (e) {}
        orig(...args);
      };
    });
  }

  function buildReport() {
    const logs = (window.__iptvErrorLogBuffer || []).slice(-150);
    const lines = [
      "=== IPTVnator error report ===",
      "timestamp: " + new Date().toISOString(),
      "href: " + location.href,
      "note: Rede Globo da lista esta MORTA. Use TV Globo RJ.",
      "",
      "=== page text ===",
      (document.body.innerText || "").slice(0, 6000),
      "",
      "=== console/traceback ===",
    ];
    if (!logs.length) lines.push("(vazio)");
    else {
      for (const l of logs) {
        lines.push("[" + l.ts + "] " + l.level + ": " + l.message);
      }
    }
    lines.push("", "=== end ===");
    return lines.join("\n");
  }

  copyBtn.onclick = async () => {
    const text = buildReport();
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand("copy");
      ta.remove();
    }
    copyBtn.textContent = ok ? "COPIADO!" : "FALHOU";
    status.textContent = ok
      ? "traceback copiado para a area de transferencia"
      : "falha ao copiar";
  };

  const GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8";
  globoBtn.onclick = async () => {
    try {
      await window.electron.openInMpv(
        GLOBO_RJ,
        "TV Globo RJ",
        "",
        "VLC/3.0.20 LibVLC/3.0.20",
        "",
        ""
      );
      status.textContent = "MPV aberto: TV Globo RJ";
    } catch (e) {
      status.textContent = "erro MPV: " + e;
    }
  };

  mpvBtn.onclick = () => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /Open in MPV/i.test(x.innerText || "")
    );
    if (b) b.click();
    else status.textContent = "botao nativo MPV nao encontrado";
  };
  vlcBtn.onclick = () => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /Open in VLC/i.test(x.innerText || "")
    );
    if (b) b.click();
    else status.textContent = "botao nativo VLC nao encontrado";
  };

  panel.appendChild(title);
  panel.appendChild(status);
  panel.appendChild(copyBtn);
  panel.appendChild(globoBtn);
  panel.appendChild(mpvBtn);
  panel.appendChild(vlcBtn);
  document.documentElement.appendChild(panel);

  return {
    panel: true,
    copy: !!document.getElementById("iptv-copy-error-logs-btn"),
    labels: [...panel.querySelectorAll("button")].map((b) => b.textContent),
  };
})();
