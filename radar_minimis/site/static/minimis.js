// Calculadora: margen de la «única empresa» (CIF + vinculados). Grupos mayores que el gratuito abren el plan Pro;
// con clave de acceso del plan, el grupo admite hasta RM.proGroupMax CIF y no hay cupo diario.
(() => {
  "use strict";
  const RM = window.RM;
  const form = document.getElementById("minimis-form");
  if (!form) return;
  const out = document.getElementById("minimis-result");
  const linkedInputs = [...form.querySelectorAll("input[name=vinculada]")];
  const NOMBRES = { general: "General", sieg: "SIEG", agricola: "Agrícola", pesca: "Pesca" };
  const ESTADO = { verde: "Margen disponible", ambar: "Vigilar", rojo: "Al límite" };

  if (RM.clave()) form.querySelectorAll(".tag-pro").forEach((b) => b.remove());

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
    if (1 + linked.length > RM.groupMax()) {
      RM.openPro("grupo_societario", cif);
      return;
    }
    out.innerHTML = '<p class="progress">Consultando la BDNS…</p>';
    try {
      const params = query(linked, form.fecha.value);
      const resp = await fetch(`${RM.api}/api/minimis/${encodeURIComponent(cif)}?${params}`, { headers: RM.authHeaders() });
      const data = await resp.json();
      if (resp.status === 402) {
        out.innerHTML = "";
        RM.openPro((data.detail && data.detail.origen) || "grupo_societario", cif);
        return;
      }
      if (!resp.ok) {
        out.innerHTML = `<p class="error">${RM.esc(RM.detail(data, "No se pudo calcular el margen."))}</p>`;
        return;
      }
      render(data, params);
    } catch (_) {
      out.innerHTML = '<p class="error">No se pudo conectar con el servicio. Inténtalo de nuevo en unos minutos.</p>';
    }
  }

  function render(d, params) {
    const pct = Math.min(100, d.utilizacion * 100);
    const general = d.regimenes.find((r) => r.regimen === "general");
    const regimenes = d.regimenes
      .map(
        (r) =>
          `<tr><td>${RM.esc(NOMBRES[r.regimen] || r.regimen)}<small>${RM.esc(r.base_legal)}</small></td><td class="num">${RM.eur(r.tope_eur)}</td>` +
          `<td class="num">${RM.eur(r.usado_eur)}</td><td class="num"><strong>${RM.eur(r.margen_eur)}</strong></td>` +
          `<td class="mono nowrap">${RM.fecha(r.ventana_desde)} – ${RM.fecha(r.ventana_hasta)}</td></tr>`,
      )
      .join("");
    const concesiones =
      d.concesiones
        .map(
          (a) =>
            `<tr><td class="mono nowrap">${RM.fecha(a.fecha_concesion)}</td><td>${RM.esc(a.concedente)}</td><td class="mono">${RM.esc(a.codigo_bdns || "—")}</td>` +
            `<td class="mono">${RM.esc(a.cif)}</td><td class="num">${RM.eur(a.importe_equivalente_eur)}</td><td>${RM.esc(NOMBRES[a.regimen] || a.regimen)}</td></tr>`,
        )
        .join("") || '<tr><td colspan="6">No constan concesiones de minimis en la ventana.</td></tr>';
    const consultas = d.consultas_bdns.map((c) => `<span class="mono">${RM.esc(c.cif)}</span> ${RM.fechaHora(c.consultado_en)}`).join(" · ");
    const informe = new URLSearchParams(params);
    informe.set("cif", d.cifs[0]);
    out.innerHTML = `
      <section class="result">
        <div class="result-head">
          <div>
            <p class="label">Margen general disponible</p>
            <p class="figure">${RM.eur(d.margen_general_eur)}</p>
            <p class="tag tag-${RM.esc(d.semaforo)}"><span class="dot dot-${RM.esc(d.semaforo)}"></span>[${RM.esc(ESTADO[d.semaforo])}]</p>
          </div>
          <div>
            <p class="label">Utilización del tope más exigente</p>
            <p class="figure">${RM.pct(d.utilizacion)}</p>
            <div class="meter sem-${RM.esc(d.semaforo)}" role="img" aria-label="Usado ${pct.toFixed(0)} % del tope"><span></span></div>
          </div>
          <div>
            <p class="label">Computado contra el tope general</p>
            <p class="figure">${RM.eur(general.usado_eur)}</p>
            <p class="small mono">${RM.fecha(d.ventana_desde)} – ${RM.fecha(d.ventana_hasta)}</p>
          </div>
        </div>
        <div class="result-body">
          <p class="small">CIF: ${d.cifs.map((c) => `<span class="mono">${RM.esc(c)}</span>`).join(", ")} · Consulta a la BDNS: ${consultas}</p>
          <h3>Régimen</h3>
          <div class="scroll"><table class="ledger"><thead><tr><th>Régimen</th><th class="num">Tope</th><th class="num">Computado</th><th class="num">Margen</th><th>Ventana</th></tr></thead><tbody>${regimenes}</tbody></table></div>
          <h3>Concesiones computadas</h3>
          <div class="scroll"><table class="ledger"><thead><tr><th>Concesión</th><th>Órgano convocante</th><th>Código BDNS</th><th>CIF</th><th class="num">Importe equivalente</th><th>Régimen</th></tr></thead><tbody>${concesiones}</tbody></table></div>
          <p class="notice">${RM.esc(d.aviso_unica_empresa)}</p>
          <ul class="warnings">${d.advertencias.map((w) => `<li>${RM.esc(w)}</li>`).join("")}</ul>
          <div class="actions">
            <a class="btn" href="/minimis/informe/?${informe}">Informe para expediente (PDF / imprimir)</a>
            <button type="button" class="btn btn-ghost" data-pro-origen="cartera_lote" data-cif="${RM.esc(d.cifs[0])}">Añadir a la cartera</button>
            <button type="button" class="btn btn-ghost" data-pro-origen="alertas_cartera" data-cif="${RM.esc(d.cifs[0])}">Vigilar concesiones nuevas</button>
          </div>
          <p class="small">${RM.esc(d.atribucion)}</p>
        </div>
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
