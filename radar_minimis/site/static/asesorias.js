// Panel de asesorías. Visitantes: demostración con datos ficticios. Clientes con licencia (clave Bearer): cartera
// real guardada en D1, importación CSV, revisión de toda la cartera contra la BDNS e informes por cliente.
// Tras el pago, Stripe vuelve con ?session_id=…: se verifica en el servidor y se muestra la clave una sola vez.
(() => {
  "use strict";
  const RM = window.RM;
  const meta = document.getElementById("panel-meta").dataset;
  const MAX_CIFS = Number(meta.maxCifs || 100);
  const ETIQUETA = { verde: "Margen disponible", ambar: "Vigilar", rojo: "Al límite" };
  const ORDEN = { rojo: 0, ambar: 1, verde: 2 };
  const CONCURRENCIA = 3;
  const $ = (id) => document.getElementById(id);
  const accessCell = $("acceso-estado");
  const accessForm = $("acceso-form");
  const clientBox = $("cliente");
  const demoBox = $("demo");
  const params = new URLSearchParams(window.location.search);
  let state = { cuenta: null, cartera: [], errores: {} };

  const api = (path, init = {}) =>
    fetch(`${RM.api}${path}`, { ...init, headers: RM.authHeaders({ "Content-Type": "application/json", ...(init.headers || {}) }) });
  const estado = (s) => (s ? `<span class="tag tag-${RM.esc(s)}"><span class="dot dot-${RM.esc(s)}"></span>[${RM.esc(ETIQUETA[s])}]</span>` : '<span class="tag">[Sin revisar]</span>');
  const formMsg = (text, error = false) => {
    const msg = accessForm.querySelector(".form-msg");
    msg.textContent = text;
    msg.classList.toggle("error", error);
  };

  // --- Demostración (datos ficticios calculados con el motor real en la generación del sitio) ----------------
  function renderDemo() {
    const data = JSON.parse($("demo-data").textContent);
    const clientes = [...data.clientes].sort((a, b) => ORDEN[a.semaforo] - ORDEN[b.semaforo] || b.utilizacion - a.utilizacion);
    const cuenta = (s) => clientes.filter((c) => c.semaforo === s).length;
    const alertas = clientes.reduce((n, c) => n + c.alertas.length, 0);
    $("panel-resumen").innerHTML =
      ["rojo", "ambar", "verde"]
        .map((s) => `<div><p class="figure">${cuenta(s)}</p><p class="tag tag-${s}"><span class="dot dot-${s}"></span>[${ETIQUETA[s]}]</p></div>`)
        .join("") + `<div><p class="figure">${alertas}</p><p class="tag">[Convocatorias compatibles]</p></div>`;
    const filas = clientes
      .map((c) => {
        const conv = c.alertas.length
          ? c.alertas
              .map((a) => `<li><a href="${RM.esc(a.url)}">${RM.esc(a.titulo)}</a><small>${a.cierre === "—" ? "Plazo no publicado" : `Cierre <span class="mono">${RM.esc(a.cierre)}</span>`}</small></li>`)
              .join("")
          : '<li class="small">Sin convocatorias compatibles abiertas</li>';
        return `<tr>
          <td>${estado(c.semaforo)}</td>
          <td><strong>${RM.esc(c.nombre)}</strong><small><span class="mono">${RM.esc(c.cif)}</span> · CNAE <span class="mono">${RM.esc(c.cnae)}</span> · ${RM.esc(c.provincia)}</small></td>
          <td class="num">${RM.eur(c.usado_general_eur)}</td>
          <td class="num"><strong>${RM.eur(c.margen_general_eur)}</strong></td>
          <td class="num">${RM.pct(c.utilizacion)}<small>${RM.esc(c.regimen_limitante)}</small></td>
          <td><ul class="plain">${conv}</ul></td>
        </tr>`;
      })
      .join("");
    $("panel").innerHTML = `<div class="scroll"><table class="ledger">
      <thead><tr><th>Estado</th><th>Cliente (ficticio)</th><th class="num">Computado general</th><th class="num">Margen</th><th class="num">Utilización</th><th>Convocatorias compatibles</th></tr></thead>
      <tbody>${filas}</tbody></table></div>`;
    RM.evento("demo_asesorias_vista");
  }

  // --- Activación tras el pago ----------------------------------------------------------------------------------
  async function activate(sessionId, attempt = 1) {
    accessCell.innerHTML = '<p class="label">Verificando el pago</p><p class="progress">Comprobando la sesión de pago con Stripe…</p>';
    try {
      const resp = await fetch(`${RM.api}/api/stripe/activar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 402 && attempt < 6) {
        setTimeout(() => activate(sessionId, attempt + 1), 3000); // el cobro puede tardar unos segundos en confirmarse
        return;
      }
      if (!resp.ok) {
        accessCell.innerHTML = `<p class="label">Activación pendiente</p><p class="error">${RM.esc(RM.detail(data, "No se pudo activar la suscripción."))}</p>`;
        return;
      }
      RM.guardarClave(data.clave);
      window.history.replaceState(null, "", "/asesorias/#cliente");
      accessCell.innerHTML = `
        <p class="label">Suscripción activada</p>
        <p>Clave de acceso de <span class="mono">${RM.esc(data.cuenta.email)}</span>. Se muestra una sola vez: guárdala en tu gestor de contraseñas. Queda guardada en este navegador.</p>
        <div class="keybox" id="clave-nueva">${RM.esc(data.clave)}</div>
        <div class="actions"><button type="button" class="btn btn-ghost" id="clave-copiar">Copiar clave</button></div>`;
      $("clave-copiar").addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(data.clave);
          $("clave-copiar").textContent = "Copiada";
        } catch (_) {
          $("clave-copiar").textContent = "Selecciona y copia la clave";
        }
      });
      loadAccount();
    } catch (_) {
      accessCell.innerHTML = '<p class="label">Activación pendiente</p><p class="error">Sin conexión. Recarga la página para reintentar la activación.</p>';
    }
  }

  // --- Cuenta y cartera -----------------------------------------------------------------------------------------
  async function loadAccount() {
    try {
      const resp = await api("/api/cuenta");
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 401) {
        RM.guardarClave("");
        formMsg("La clave no es válida o ha sido sustituida por otra más reciente.", true);
        return;
      }
      if (resp.status === 402) {
        formMsg(RM.detail(data, "La suscripción no está activa."), true);
        accessForm.insertAdjacentHTML("beforeend", '<button type="button" class="btn-text" data-accion="portal">Abrir el portal de cliente</button>');
        return;
      }
      if (!resp.ok) {
        formMsg(RM.detail(data, "No se pudo cargar la cuenta."), true);
        return;
      }
      state = { cuenta: data.cuenta, cartera: data.cartera, errores: {} };
      if (document.getElementById("clave-nueva")) accessForm.hidden = true; // se mantiene visible la clave recién emitida
      else $("acceso").hidden = true;
      demoBox.hidden = true;
      clientBox.hidden = false;
      renderClient();
      const pending = RM.clean(params.get("anadir"));
      if (pending) $("c-cif").value = pending;
      if (window.location.hash === "#cliente") clientBox.scrollIntoView();
    } catch (_) {
      formMsg("Sin conexión con el servicio.", true);
    }
  }

  function renderClient() {
    const c = state.cuenta;
    clientBox.innerHTML = `
      <div class="block-head">
        <h2>Cartera de clientes</h2>
        <span class="small"><span class="mono">${RM.esc(c.email)}</span> · ${RM.esc(c.precio)} · <span class="mono" id="c-total"></span></span>
      </div>
      <div class="toolbar">
        <button type="button" class="btn" data-accion="revisar">Revisar cartera</button>
        <label class="btn btn-ghost" for="c-csv">Importar CSV</label>
        <input type="file" id="c-csv" accept=".csv,.txt,text/csv,text/plain" hidden>
        <button type="button" class="btn btn-ghost" data-accion="exportar">Exportar CSV</button>
        <span class="spacer"></span>
        <button type="button" class="btn-text" data-accion="portal">Gestionar suscripción</button>
        <button type="button" class="btn-text" data-accion="salir">Cerrar sesión</button>
      </div>
      <form id="c-add" class="add-row" autocomplete="off">
        <div class="stack"><label for="c-cif">CIF</label><input id="c-cif" class="mono" required spellcheck="false" placeholder="B12345674"></div>
        <div class="stack"><label for="c-alias">Nombre del cliente</label><input id="c-alias" maxlength="120" placeholder="Opcional"></div>
        <div class="stack"><label for="c-vinc">CIF vinculados (hasta ${RM.esc(c.max_vinculadas)}, separados por «|»)</label><input id="c-vinc" class="mono" spellcheck="false" placeholder="A11111119|B00000000"></div>
        <button class="btn btn-ghost">Añadir</button>
      </form>
      <p class="small">CSV: una fila por cliente con las columnas <span class="mono">cif;nombre;vinculadas</span> (cabecera opcional; separador «;», «,» o tabulador). Solo CIF de personas jurídicas.</p>
      <p class="progress" id="c-progress" aria-live="polite"></p>
      <div id="c-rechazos" class="rejected"></div>
      <div class="grid grid-4 summary" id="c-resumen"></div>
      <div class="scroll"><table class="ledger" id="c-tabla"></table></div>`;
    $("c-add").addEventListener("submit", addOne);
    $("c-csv").addEventListener("change", importCsv);
    renderPortfolio();
  }

  function renderPortfolio() {
    const rows = [...state.cartera].sort(
      (a, b) => (ORDEN[a.semaforo] ?? 3) - (ORDEN[b.semaforo] ?? 3) || (b.utilizacion ?? -1) - (a.utilizacion ?? -1) || a.cif.localeCompare(b.cif),
    );
    $("c-total").textContent = `${rows.length}/${MAX_CIFS} CIF`;
    const count = (s) => rows.filter((r) => r.semaforo === s).length;
    const nuevas = rows.reduce((n, r) => n + (r.concesiones_nuevas || []).length, 0);
    $("c-resumen").innerHTML =
      ["rojo", "ambar", "verde"]
        .map((s) => `<div><p class="figure">${count(s)}</p><p class="tag tag-${s}"><span class="dot dot-${s}"></span>[${ETIQUETA[s]}]</p></div>`)
        .join("") + `<div><p class="figure">${nuevas}</p><p class="tag ${nuevas ? "tag-alerta" : ""}">[Concesiones nuevas]</p></div>`;
    if (!rows.length) {
      $("c-tabla").innerHTML = '<tbody><tr><td>La cartera está vacía. Añade un CIF o importa un CSV.</td></tr></tbody>';
      return;
    }
    const body = rows
      .map((r) => {
        const informe = new URLSearchParams({ cif: r.cif });
        if (r.vinculadas.length) informe.set("vinculadas", r.vinculadas.join(","));
        const error = state.errores[r.cif];
        const novedades = (r.concesiones_nuevas || []).length
          ? `<span class="tag tag-alerta">[${r.concesiones_nuevas.length} nueva${r.concesiones_nuevas.length === 1 ? "" : "s"}]</span>`
          : '<span class="small">—</span>';
        return `<tr>
          <td>${estado(r.semaforo)}</td>
          <td><strong>${RM.esc(r.alias || "Sin nombre")}</strong><small><span class="mono">${RM.esc(r.cif)}</span>${r.vinculadas.length ? ` + ${r.vinculadas.map((v) => `<span class="mono">${RM.esc(v)}</span>`).join(", ")}` : ""}</small>${error ? `<small class="error">${RM.esc(error)}</small>` : ""}</td>
          <td class="num">${r.usado_eur == null ? "—" : RM.eur(r.usado_eur)}</td>
          <td class="num"><strong>${r.margen_eur == null ? "—" : RM.eur(r.margen_eur)}</strong></td>
          <td class="num">${r.utilizacion == null ? "—" : RM.pct(r.utilizacion)}</td>
          <td class="mono nowrap">${RM.fecha(r.ultima_revision)}</td>
          <td>${novedades}</td>
          <td class="nowrap"><a href="/minimis/informe/?${informe}">Informe</a> · <button type="button" class="btn-text" data-accion="quitar" data-cif="${RM.esc(r.cif)}">Quitar</button></td>
        </tr>`;
      })
      .join("");
    $("c-tabla").innerHTML = `<thead><tr><th>Estado</th><th>Cliente</th><th class="num">Computado general</th><th class="num">Margen</th><th class="num">Utilización</th><th>Revisión</th><th>Novedades</th><th></th></tr></thead><tbody>${body}</tbody>`;
  }

  function showRejected(rechazados) {
    const box = $("c-rechazos");
    if (!rechazados.length) {
      box.innerHTML = "";
      return;
    }
    const items = rechazados
      .slice(0, 20)
      .map((r) => `<li>${r.fila ? `Fila <span class="mono">${r.fila}</span>: ` : ""}<span class="mono">${RM.esc(r.valor)}</span> · ${RM.esc(r.motivo)}</li>`)
      .join("");
    box.innerHTML = `<p>${rechazados.length} fila(s) no importada(s):</p><ul>${items}</ul>${rechazados.length > 20 ? "<p>…</p>" : ""}`;
  }

  async function save(clientes) {
    const progress = $("c-progress");
    const rechazados = [];
    let guardados = 0;
    for (let i = 0; i < clientes.length; i += 500) {
      progress.textContent = `Guardando ${Math.min(i + 500, clientes.length)}/${clientes.length}…`;
      const resp = await api("/api/cuenta/cartera", { method: "POST", body: JSON.stringify({ clientes: clientes.slice(i, i + 500) }) });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        progress.textContent = RM.detail(data, "No se pudo guardar la cartera.");
        return false;
      }
      guardados += data.guardados;
      rechazados.push(...data.rechazados.map((r) => ({ ...r, fila: r.fila ? r.fila + i : null })));
      state.cartera = data.cartera;
    }
    progress.textContent = `${guardados} cliente(s) guardado(s).`;
    showRejected(rechazados);
    renderPortfolio();
    return true;
  }

  async function addOne(event) {
    event.preventDefault();
    const ok = await save([{ cif: $("c-cif").value, alias: $("c-alias").value, vinculadas: $("c-vinc").value }]);
    if (ok) event.target.reset();
  }

  /** CSV con o sin cabecera; separador «;», «,» o tabulador; campos entre comillas con "" escapadas. */
  function parseCsv(text) {
    const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) return [];
    const sep = [";", "\t", ","].map((s) => [s, lines[0].split(s).length]).sort((a, b) => b[1] - a[1])[0][0];
    const split = (line) => {
      const out = [];
      let cur = "";
      let quoted = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (quoted) {
          if (ch === '"' && line[i + 1] === '"') {
            cur += '"';
            i += 1;
          } else if (ch === '"') quoted = false;
          else cur += ch;
        } else if (ch === '"') quoted = true;
        else if (ch === sep) {
          out.push(cur.trim());
          cur = "";
        } else cur += ch;
      }
      out.push(cur.trim());
      return out;
    };
    const rows = lines.map(split);
    let idx = { cif: 0, alias: 1, vinculadas: 2 };
    if (!/^[A-Z]\d{7}[0-9A-J]$|^\d{8}[A-Z]$|^[XYZ]\d{7}[A-Z]$/.test(RM.clean(rows[0][0]))) {
      const head = rows.shift().map((h) => h.toLowerCase());
      const find = (re, fallback) => {
        const i = head.findIndex((h) => re.test(h));
        return i === -1 ? fallback : i;
      };
      idx = { cif: find(/cif|nif/, 0), alias: find(/nombre|alias|raz|cliente|empresa/, 1), vinculadas: find(/vincul|grupo/, 2) };
    }
    return rows.map((r) => ({ cif: r[idx.cif] || "", alias: r[idx.alias] || "", vinculadas: r[idx.vinculadas] || "" }));
  }

  async function importCsv(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 1_000_000) {
      $("c-progress").textContent = "El fichero supera 1 MB.";
      return;
    }
    const clientes = parseCsv(await file.text());
    if (!clientes.length) {
      $("c-progress").textContent = "El fichero no contiene filas.";
      return;
    }
    await save(clientes);
  }

  async function review() {
    const button = clientBox.querySelector('[data-accion="revisar"]');
    const rows = [...state.cartera];
    if (!rows.length) return;
    button.disabled = true;
    state.errores = {};
    let done = 0;
    const progress = $("c-progress");
    const queue = [...rows];
    async function worker() {
      while (queue.length) {
        const r = queue.shift();
        const q = new URLSearchParams();
        if (r.vinculadas.length) q.set("vinculadas", r.vinculadas.join(","));
        try {
          const resp = await api(`/api/minimis/${encodeURIComponent(r.cif)}?${q}`);
          const data = await resp.json().catch(() => ({}));
          if (resp.ok) {
            Object.assign(r, {
              usado_eur: data.regimenes.find((x) => x.regimen === "general").usado_eur,
              margen_eur: data.margen_general_eur,
              utilizacion: data.utilizacion,
              semaforo: data.semaforo,
              ultima_revision: new Date().toISOString(),
              concesiones_nuevas: data.revision ? data.revision.concesiones_nuevas : [],
            });
          } else state.errores[r.cif] = RM.detail(data, `Error ${resp.status}`);
        } catch (_) {
          state.errores[r.cif] = "Sin conexión con la BDNS";
        }
        done += 1;
        progress.textContent = `Revisados ${done}/${rows.length}`;
        state.cartera = state.cartera.map((x) => (x.cif === r.cif ? r : x));
        renderPortfolio();
      }
    }
    await Promise.all(Array.from({ length: Math.min(CONCURRENCIA, rows.length) }, worker));
    const failed = Object.keys(state.errores).length;
    progress.textContent = `Revisión completada: ${rows.length - failed}/${rows.length} CIF${failed ? ` · ${failed} con error` : ""}.`;
    button.disabled = false;
  }

  function exportCsv() {
    const head = ["cif", "nombre", "vinculadas", "estado", "computado_general_eur", "margen_eur", "utilizacion", "ultima_revision", "concesiones_nuevas"];
    const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = state.cartera.map((r) =>
      [r.cif, r.alias, r.vinculadas.join("|"), r.semaforo ? ETIQUETA[r.semaforo] : "", r.usado_eur, r.margen_eur, r.utilizacion, r.ultima_revision, (r.concesiones_nuevas || []).join("|")]
        .map(cell)
        .join(";"),
    );
    const blob = new Blob(["﻿" + [head.join(";"), ...lines].join("\r\n")], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `cartera-minimis-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  async function portal(button) {
    button.disabled = true;
    try {
      const resp = await api("/api/cuenta/portal", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.url) {
        window.location.href = data.url;
        return;
      }
      window.alert(RM.detail(data, "No se pudo abrir el portal de cliente."));
    } catch (_) {
      window.alert("Sin conexión con el servicio.");
    }
    button.disabled = false;
  }

  async function remove(cif) {
    const resp = await api(`/api/cuenta/cartera?cif=${encodeURIComponent(cif)}`, { method: "DELETE" });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      state.cartera = data.cartera;
      renderPortfolio();
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-accion]");
    if (!button) return;
    const action = button.dataset.accion;
    if (action === "revisar") review();
    else if (action === "exportar") exportCsv();
    else if (action === "portal") portal(button);
    else if (action === "quitar") remove(button.dataset.cif);
    else if (action === "salir") {
      RM.guardarClave("");
      window.location.href = "/asesorias/";
    }
  });

  accessForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const clave = accessForm.clave.value.trim();
    if (!/^rm_[A-Za-z0-9_-]{32,64}$/.test(clave)) {
      formMsg("La clave tiene el formato rm_ seguido de 43 caracteres.", true);
      return;
    }
    RM.guardarClave(clave);
    formMsg("Comprobando la clave…");
    loadAccount();
  });

  renderDemo();
  if (params.get("pago") === "cancelado") formMsg("Pago cancelado: no se ha realizado ningún cargo.");
  if (params.get("session_id")) activate(params.get("session_id"));
  else if (RM.clave()) loadAccount();
})();
