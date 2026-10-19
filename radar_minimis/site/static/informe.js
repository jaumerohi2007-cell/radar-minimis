// Informe para expediente: se compone en el navegador y se guarda como PDF con «Imprimir» (0 € de servidor).
(() => {
  "use strict";
  const RM = window.RM;
  const root = document.getElementById("informe");
  const printBtn = document.getElementById("inf-print");
  const meta = document.getElementById("inf-meta").dataset;
  const NOMBRES = { general: "General", sieg: "SIEG", agricola: "Agrícola", pesca: "Pesca" };
  const params = new URLSearchParams(window.location.search);
  const cif = RM.clean(params.get("cif"));

  /** Número de control: SHA-256 de los CIF, las concesiones y la hora de consulta. Mismo dato, mismo número. */
  async function referencia(data) {
    try {
      const bytes = new TextEncoder().encode(JSON.stringify([data.cifs, data.concesiones, data.consultas_bdns]));
      const hash = await crypto.subtle.digest("SHA-256", bytes);
      const hex = [...new Uint8Array(hash)].slice(0, 6).map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
      return `RM-${hex.slice(0, 4)}-${hex.slice(4, 8)}-${hex.slice(8)}`;
    } catch (_) {
      return "RM-" + Date.now().toString(36).toUpperCase();
    }
  }

  async function load() {
    if (!cif) {
      root.innerHTML = '<p class="error">Falta el CIF. <a href="/minimis/">Volver a la calculadora</a>.</p>';
      return;
    }
    const q = new URLSearchParams({ fresco: "1" });
    for (const key of ["vinculadas", "fecha"]) if (params.get(key)) q.set(key, params.get(key));
    try {
      const resp = await fetch(`${RM.api}/api/minimis/${encodeURIComponent(cif)}?${q}`, { headers: RM.authHeaders() });
      const data = await resp.json();
      if (resp.status === 402) {
        root.innerHTML = "<p>Los informes de grupos de más CIF forman parte del plan Asesorías Pro.</p>";
        RM.openPro("grupo_societario", cif);
        return;
      }
      if (!resp.ok) {
        root.innerHTML = `<p class="error">${RM.esc(RM.detail(data, "No se pudo generar el informe."))}</p>`;
        return;
      }
      render(data, await referencia(data));
      printBtn.disabled = false;
      RM.evento("informe_generado");
    } catch (_) {
      root.innerHTML = '<p class="error">No se pudo conectar con la BDNS. Inténtalo de nuevo en unos minutos.</p>';
    }
  }

  const sec = (n, title) => `<h2><span class="sec">§${n}</span>${title}</h2>`;
  const mono = (s) => `<span class="mono">${RM.esc(s)}</span>`;

  function render(d, ref) {
    const principal = d.cifs[0];
    const nombre = d.beneficiarios[principal] || "[Razón social]";
    const vinculadas = d.cifs.slice(1);
    const general = d.regimenes.find((r) => r.regimen === "general");
    const emitido = new Date().toISOString();
    const filas = d.concesiones
      .map(
        (a) =>
          `<tr><td class="mono">${RM.fecha(a.fecha_concesion)}</td><td>${RM.esc(a.concedente)}</td><td class="mono">${RM.esc(a.codigo_bdns || "—")}</td>` +
          `<td class="mono">${RM.esc(a.cif)}</td><td>${RM.esc(a.reglamento)}</td><td class="num">${RM.eur(a.importe_equivalente_eur)}</td></tr>`,
      )
      .join("");
    const resumen = d.regimenes
      .map(
        (r) =>
          `<tr><td>${RM.esc(NOMBRES[r.regimen] || r.regimen)}</td><td class="num">${RM.eur(r.tope_eur)}</td><td class="num">${RM.eur(r.usado_eur)}</td>` +
          `<td class="num"><strong>${RM.eur(r.margen_eur)}</strong></td><td>${RM.esc(r.base_legal)}</td></tr>`,
      )
      .join("");
    const consultas = d.consultas_bdns
      .map((c) => `<li>${mono(c.cif)}: ${RM.esc(RM.fechaHora(c.consultado_en))} · ${mono(c.n_concesiones)} concesión(es) de minimis</li>`)
      .join("");
    root.innerHTML = `
      <header class="inf-head">
        <div><p class="brand-doc">Radar Minimis</p><p class="small">Informe orientativo. No es un certificado oficial.</p></div>
        <div class="small mono">${RM.esc(ref)}</div>
      </header>
      <div class="inf-control">
        <div><span>N.º de control</span><strong>${RM.esc(ref)}</strong></div>
        <div><span>Emitido</span><strong>${RM.fecha(emitido)} ${new Date(emitido).toLocaleTimeString("es-ES", { timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit" })}</strong></div>
        <div><span>CIF principal</span><strong>${RM.esc(principal)}</strong></div>
        <div><span>Fecha de referencia</span><strong>${RM.fecha(d.fecha_referencia)}</strong></div>
      </div>
      <h1>Informe de ayudas de minimis para expediente</h1>
      <p class="inf-sub">Concesiones de minimis registradas en la Base de Datos Nacional de Subvenciones (BDNS) en los tres años móviles, fecha a fecha, anteriores a la fecha de referencia.</p>
      <section>${sec(1, "Datos de la consulta")}
        <table class="inf-kv">
          <tr><th>Empresa</th><td>${RM.esc(nombre)}</td></tr>
          <tr><th>CIF consultado</th><td class="mono">${RM.esc(principal)}</td></tr>
          <tr><th>CIF vinculados («única empresa»)</th><td>${vinculadas.length ? vinculadas.map(mono).join(", ") : "Ninguno indicado"}</td></tr>
          <tr><th>Fecha de referencia del cómputo</th><td>${mono(RM.fecha(d.fecha_referencia))} ${d.fecha_referencia_indicada ? "(fecha prevista de concesión)" : "(día de la consulta)"}</td></tr>
          <tr><th>Ventana computada</th><td>Del ${mono(RM.fecha(d.ventana_desde))} al ${mono(RM.fecha(d.ventana_hasta))}, ambos incluidos</td></tr>
          <tr><th>Consulta a la BDNS (fecha y hora)</th><td><ul class="plain">${consultas}</ul></td></tr>
        </table>
      </section>
      <section>${sec(2, "Concesiones computadas")}
        <table class="inf-table">
          <thead><tr><th>Fecha de concesión</th><th>Órgano convocante</th><th>Código BDNS</th><th>CIF</th><th>Reglamento</th><th class="num">Importe equivalente (subvención bruta)</th></tr></thead>
          <tbody>${filas || '<tr><td colspan="6">No constan concesiones de minimis en la ventana.</td></tr>'}</tbody>
          <tfoot><tr><td colspan="5">Total computado contra el tope general</td><td class="num">${RM.eur(general.usado_eur)}</td></tr></tfoot>
        </table>
      </section>
      <section>${sec(3, "Margen disponible")}
        <table class="inf-table">
          <thead><tr><th>Régimen</th><th class="num">Tope</th><th class="num">Computado</th><th class="num">Margen disponible</th><th>Base legal</th></tr></thead>
          <tbody>${resumen}</tbody>
        </table>
        <p class="inf-note">${RM.esc(d.criterio_acumulacion)}</p>
      </section>
      <section>${sec(4, "«Única empresa»")}<p>${RM.esc(d.aviso_unica_empresa)}</p></section>
      <section class="inf-decl">${sec(5, "Borrador de declaración responsable")}
        <p>D./D.ª ________________________________, con DNI/NIE ______________, en representación de ${RM.esc(nombre)}, con CIF ${mono(principal)}, DECLARA bajo su responsabilidad que la empresa${vinculadas.length ? `, junto con las empresas con las que forma una «única empresa» (${vinculadas.map(mono).join(", ")}),` : ""} ha recibido en los tres años anteriores a la fecha de concesión las ayudas de minimis relacionadas en el §2, por un importe total de ${RM.eur(general.usado_eur)}, y que no ha recibido otras ayudas de minimis distintas de las siguientes: ______________________________________________.</p>
        <p>En ____________________, a ____ de ________________ de ________. &nbsp; Firma: ______________________</p>
        <p class="inf-note">Borrador orientativo: adáptalo al modelo que exijan las bases de cada convocatoria.</p>
      </section>
      <section>${sec(6, "Advertencias")}<ul>${d.advertencias.map((w) => `<li>${RM.esc(w)}</li>`).join("")}</ul></section>
      <footer class="inf-foot">
        <p>${RM.esc(meta.attribution)}. Datos consultados en el momento indicado en el §1; los datos de la BDNS son dinámicos y pueden corregirse con posterioridad.</p>
        <p>Normativa aplicada: Reg. (UE) 2023/2831 (general), Reg. (UE) 2023/2832 (SIEG), Reg. (UE) 1408/2013 (agrícola) y Reg. (UE) 717/2014 (pesca), en sus versiones vigentes.</p>
        <p>${RM.esc(meta.disclaimer)} Este informe no es un certificado oficial ni constituye asesoramiento jurídico. Emitido por ${RM.esc(meta.owner)} mediante Radar Minimis · N.º de control ${RM.esc(ref)}.</p>
      </footer>`;
  }

  printBtn.addEventListener("click", () => {
    RM.evento("informe_impreso");
    window.print();
  });
  load();
})();
