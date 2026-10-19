// Calculadora: margen de la «única empresa» (CIF + vinculados). Grupos mayores que el gratuito abren Asesorías Pro.
(() => {
  "use strict";
  const RM = window.RM;
  const form = document.getElementById("minimis-form");
  if (!form) return;
  const out = document.getElementById("minimis-result");
  const linkedInputs = [...form.querySelectorAll("input[name=vinculada]")];
  const NOMBRES = { general: "General (300.000 €)", sieg: "SIEG (750.000 €)", agricola: "Agrícola", pesca: "Pesca" };
  const SEMAFORO = { verde: "Margen holgado", ambar: "Vigilar", rojo: "Cerca o por encima del tope" };

  function query(linked, fecha) {
    const params = new URLSearchParams();
    if (linked.length) params.set("vinculadas", linked.join(","));
    if (fecha) params.set("fecha", fecha);
    return params;
  }

  async function submit() {
    const cif = RM.clean(form.cif.value);
    const linked = [...new Set(linkedInputs.map((i) => RM.clean(i.value)).filter((v) => v && v !== cif))];
    RM.lastCif = cif;
    if (1 + linked.length > RM.freeGroupMax) {
      RM.openPro("grupo_societario", cif);
      return;
    }
    out.innerHTML = "<p>Consultando la BDNS…</p>";
    try {
      const params = query(linked, form.fecha.value);
      const resp = await fetch(`${RM.api}/api/minimis/${encodeURIComponent(cif)}?${params}`);
      const data = await resp.json();
      if (resp.status === 402) {
        out.innerHTML = "";
        RM.openPro((data.detail && data.detail.origen) || "grupo_societario", cif);
        return;
      }
      if (!resp.ok) {
        out.innerHTML = `<p class="error">${RM.esc(typeof data.detail === "string" ? data.detail : "No se pudo calcular el margen.")}</p>`;
        return;
      }
      render(data, params);
    } catch (_) {
      out.innerHTML = '<p class="error">No se pudo conectar con el servicio. Inténtalo de nuevo en unos minutos.</p>';
    }
  }

  function render(d, params) {
    const pct = Math.min(100, d.utilizacion * 100);
    const regimenes = d.regimenes
      .map(
        (r) =>
          `<tr><td>${RM.esc(NOMBRES[r.regimen] || r.regimen)}</td><td>${RM.eur(r.usado_eur)}</td><td>${RM.eur(r.tope_eur)}</td>` +
          `<td><strong>${RM.eur(r.margen_eur)}</strong></td><td>${RM.fecha(r.ventana_desde)} – ${RM.fecha(r.ventana_hasta)}</td></tr>`,
      )
      .join("");
    const concesiones =
      d.concesiones
        .map(
          (a) =>
            `<tr><td>${RM.fecha(a.fecha_concesion)}</td><td>${RM.esc(a.concedente)}</td><td>${RM.esc(a.codigo_bdns || "—")}</td>` +
            `<td>${RM.eur(a.importe_equivalente_eur)}</td><td>${RM.esc(a.regimen)}</td></tr>`,
        )
        .join("") || '<tr><td colspan="5">No hay concesiones de minimis registradas en el período.</td></tr>';
    const consultas = d.consultas_bdns.map((c) => `${RM.esc(c.cif)}: ${RM.fechaHora(c.consultado_en)}`).join(" · ");
    const informe = new URLSearchParams(params);
    informe.set("cif", d.cifs[0]);
    out.innerHTML = `
      <section class="result sem-borde-${RM.esc(d.semaforo)}">
        <h2>Margen general disponible: ${RM.eur(d.margen_general_eur)}</h2>
        <p><span class="sem sem-${RM.esc(d.semaforo)}"></span> ${RM.esc(SEMAFORO[d.semaforo])} · ${pct.toFixed(0)} % del tope más exigente</p>
        <div class="meter" role="img" aria-label="Usado ${pct.toFixed(0)} % del tope"><span></span></div>
        <p class="small">Ventana: ${RM.fecha(d.ventana_desde)} – ${RM.fecha(d.ventana_hasta)} · CIF: ${d.cifs.map(RM.esc).join(", ")} · Consulta a la BDNS: ${consultas}</p>
        <table class="list"><thead><tr><th>Régimen</th><th>Usado</th><th>Tope</th><th>Margen</th><th>Ventana</th></tr></thead><tbody>${regimenes}</tbody></table>
        <h3>Concesiones computadas</h3>
        <table class="list"><thead><tr><th>Fecha</th><th>Órgano convocante</th><th>Código BDNS</th><th>Importe equivalente</th><th>Régimen</th></tr></thead><tbody>${concesiones}</tbody></table>
        <p class="notice">${RM.esc(d.aviso_unica_empresa)}</p>
        <ul class="warnings">${d.advertencias.map((w) => `<li>${RM.esc(w)}</li>`).join("")}</ul>
        <div class="actions">
          <a class="button" href="/minimis/informe/?${informe}">Generar Informe de Minimis para Expediente (PDF / Imprimir)</a>
          <button type="button" class="secondary" data-pro-origen="cartera_lote" data-cif="${RM.esc(d.cifs[0])}">Vigilar este CIF y toda mi cartera</button>
          <button type="button" class="secondary" data-pro-origen="alertas_cartera" data-cif="${RM.esc(d.cifs[0])}">Recibir alertas semanales de nuevas subvenciones</button>
        </div>
        <p class="small">${RM.esc(d.atribucion)}</p>
      </section>`;
    // CSSOM en lugar de style="" inline: compatible con la CSP style-src 'self'.
    out.querySelector(".meter > span").style.width = `${pct}%`;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  const preset = new URLSearchParams(window.location.search).get("cif");
  if (preset) {
    form.cif.value = preset;
    submit();
  }
})();
