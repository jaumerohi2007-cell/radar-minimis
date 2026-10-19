// Utilidades compartidas. Configuración en atributos data-* del <body> (sin JS inline: CSP script-src 'self').
window.RM = (() => {
  "use strict";
  const cfg = document.body.dataset;
  const base = (v) => (v || "").replace(/\/$/, "");
  const KEY_STORE = "rm_clave";
  const RM = {
    api: base(cfg.api),
    leadsApi: base(cfg.leadsApi),
    billing: cfg.billing || "validation",
    checkout: cfg.checkout || "",
    freeGroupMax: Number(cfg.freeGroupMax || 2),
    proGroupMax: Number(cfg.proGroupMax || 4),
    lastCif: "",
  };
  RM.esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  RM.eur = (n) =>
    Number(n || 0).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" }) + " €";
  RM.pct = (x) => `${(Number(x || 0) * 100).toLocaleString("es-ES", { maximumFractionDigits: 1 })} %`;
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
        }) + " (hora de Madrid)"
      : "—";

  // Clave de acceso del plan: solo en este navegador; si el almacenamiento falla, la sesión dura lo que la página.
  let memoryKey = "";
  RM.clave = () => {
    try {
      return window.localStorage.getItem(KEY_STORE) || memoryKey;
    } catch (_) {
      return memoryKey;
    }
  };
  RM.guardarClave = (clave) => {
    memoryKey = clave || "";
    try {
      if (clave) window.localStorage.setItem(KEY_STORE, clave);
      else window.localStorage.removeItem(KEY_STORE);
    } catch (_) {
      /* modo privado o almacenamiento bloqueado */
    }
  };
  RM.authHeaders = (extra = {}) => {
    const clave = RM.clave();
    return clave ? { ...extra, Authorization: `Bearer ${clave}` } : extra;
  };
  RM.groupMax = () => (RM.clave() ? RM.proGroupMax : RM.freeGroupMax);
  RM.detail = (data, fallback) => (typeof data?.detail === "string" ? data.detail : data?.detail?.mensaje || fallback);

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
