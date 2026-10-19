// Puerta de acceso a Asesorías Pro. En BILLING_MODE=validation abre la lista de espera; en stripe, el pago.
(() => {
  "use strict";
  const RM = window.RM;
  const modal = document.getElementById("pro-modal");
  const form = modal ? modal.querySelector("form") : null;
  const ok = modal ? modal.querySelector(".modal-ok") : null;

  function open(origen, cif) {
    RM.evento(`modal_${origen}`);
    if (RM.billing !== "validation") {
      if (RM.checkout) window.location.href = RM.checkout;
      return;
    }
    if (!modal) return;
    form.reset();
    form.hidden = false;
    ok.hidden = true;
    form.origen_clic.value = origen;
    form.cif_consultado.value = cif || "";
    form.querySelector(".form-msg").textContent = "";
    modal.hidden = false;
    form.email.focus();
  }

  function close() {
    if (modal) modal.hidden = true;
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-pro-origen]");
    if (trigger) {
      event.preventDefault();
      open(trigger.dataset.proOrigen, trigger.dataset.cif || RM.lastCif);
      return;
    }
    if (event.target.closest("[data-modal-close]") || event.target === modal) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = form.querySelector(".form-msg");
      if (!form.reportValidity()) return;
      const payload = {
        email: form.email.value.trim(),
        num_cifs_estimados: Number(form.num_cifs_estimados.value),
        origen_clic: form.origen_clic.value,
        cif_consultado: form.cif_consultado.value,
        consentimiento: form.consentimiento.checked,
        web: form.web.value,
      };
      msg.textContent = "Enviando…";
      try {
        const resp = await fetch(`${RM.leadsApi}/api/waitlist`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          msg.textContent = typeof data.detail === "string" ? data.detail : "No se pudo enviar. Inténtalo de nuevo.";
          return;
        }
        form.hidden = true;
        ok.textContent = data.mensaje || "¡Gracias! Te escribiremos por orden de solicitud.";
        ok.hidden = false;
      } catch (_) {
        msg.textContent = "Sin conexión. Inténtalo de nuevo en unos segundos.";
      }
    });
  }
  RM.openPro = open;
})();
