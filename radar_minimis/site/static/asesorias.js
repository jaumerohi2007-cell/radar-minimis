// Panel demo de cartera para asesorías: datos ficticios calculados con el motor real en la generación del sitio.
(() => {
  "use strict";
  const RM = window.RM;
  const data = JSON.parse(document.getElementById("demo-data").textContent);
  const panel = document.getElementById("panel");
  const resumen = document.getElementById("panel-resumen");
  const ETIQUETA = { verde: "Holgado", ambar: "Vigilar", rojo: "Al límite" };
  const ORDEN = { rojo: 0, ambar: 1, verde: 2 };
  const clientes = [...data.clientes].sort((a, b) => ORDEN[a.semaforo] - ORDEN[b.semaforo] || b.utilizacion - a.utilizacion);

  const cuenta = (s) => clientes.filter((c) => c.semaforo === s).length;
  const alertas = clientes.reduce((n, c) => n + c.alertas.length, 0);
  resumen.innerHTML = ["rojo", "ambar", "verde"]
    .map((s) => `<div class="card"><span class="sem sem-${s}"></span> <strong>${cuenta(s)}</strong> ${ETIQUETA[s].toLowerCase()}</div>`)
    .join("") + `<div class="card"><strong>${alertas}</strong> convocatorias compatibles abiertas</div>`;

  const filas = clientes
    .map((c) => {
      const conv = c.alertas.length
        ? c.alertas.map((a) => `<li><a href="${RM.esc(a.url)}">${RM.esc(a.titulo)}</a> <small>${a.cierre === "—" ? "plazo no publicado" : `cierra ${RM.esc(a.cierre)}`}</small></li>`).join("")
        : "<li><small>Sin convocatorias nuevas compatibles esta semana</small></li>";
      return `<tr>
        <td><span class="sem sem-${RM.esc(c.semaforo)}" title="${RM.esc(ETIQUETA[c.semaforo])}"></span></td>
        <td><strong>${RM.esc(c.nombre)}</strong><br><small>${RM.esc(c.cif)} · CNAE ${RM.esc(c.cnae)} · ${RM.esc(c.provincia)}</small></td>
        <td class="num">${RM.eur(c.usado_general_eur)}</td>
        <td class="num"><strong>${RM.eur(c.margen_general_eur)}</strong></td>
        <td class="num">${(c.utilizacion * 100).toFixed(0)} %<br><small>${RM.esc(c.regimen_limitante)}</small></td>
        <td><ul class="plain">${conv}</ul></td>
      </tr>`;
    })
    .join("");
  panel.innerHTML = `<table class="list panel">
    <thead><tr><th></th><th>Cliente (ficticio)</th><th class="num">Usado (general)</th><th class="num">Margen</th><th class="num">Tope más exigente</th><th>Alertas: convocatorias compatibles</th></tr></thead>
    <tbody>${filas}</tbody></table>`;
  RM.evento("demo_asesorias_vista");
})();
