// Utilidades compartidas. Configuración en atributos data-* del <body> (sin JS inline: CSP script-src 'self').
window.RM = (() => {
  "use strict";
  const cfg = document.body.dataset;
  const base = (v) => (v || "").replace(/\/$/, "");
  const RM = {
    api: base(cfg.api),
    leadsApi: base(cfg.leadsApi),
    billing: cfg.billing || "validation",
    checkout: cfg.checkout || "",
    freeGroupMax: Number(cfg.freeGroupMax || 2),
    lastCif: "",
  };
  RM.esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  RM.eur = (n) => Number(n || 0).toLocaleString("es-ES", { maximumFractionDigits: 2 }) + " €";
  RM.clean = (v) => String(v || "").toUpperCase().replace(/[\s.\-/]/g, "");
  RM.fecha = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");
  RM.fechaHora = (iso) =>
    iso
      ? new Date(iso).toLocaleString("es-ES", {
          timeZone: "Europe/Madrid",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }) +
        " (hora de Madrid)"
      : "—";
  // Métrica agregada (sin cookies ni identificadores): solo el nombre del evento.
  RM.evento = (tipo) => {
    try {
      const body = JSON.stringify({ tipo });
      const url = `${RM.leadsApi}/api/evento`;
      if (navigator.sendBeacon) navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      else fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
    } catch (_) {
      /* la medición nunca rompe la página */
    }
  };
  return RM;
})();
