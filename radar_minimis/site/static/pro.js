// Puerta del plan Asesorías Pro. BILLING_MODE=validation: lista de espera. BILLING_MODE=stripe: resumen del plan y
// Stripe Checkout (POST /api/checkout). Con una clave de acceso guardada, las funciones del plan llevan al panel.
(() => {
  "use strict";
  const RM = window.RM;
  const waitlist = document.getElementById("pro-modal");
  const plan = document.getElementById("plan-modal");
  const modal = waitlist || plan;
  const form = waitlist ? waitlist.querySelector("form") : null;
  const ok = waitlist ? waitlist.querySelector(".modal-ok") : null;
  let current = { origen: "", cif: "" };

  function open(origen, cif) {
    RM.evento(`modal_${origen}`);
    current = { origen, cif: cif || "" };
    if (RM.clave()) {
      // Cliente con licencia: las funciones del plan están en su panel.
      if (window.location.pathname === "/asesorias/") document.getElementById("cliente")?.scrollIntoView();
      else window.location.href = cif ? `/asesorias/?anadir=${encodeURIComponent(cif)}#cliente` : "/asesorias/#cliente";
      return;
    }
    if (plan) {
      plan.querySelector(".form-msg").textContent = "";
      plan.hidden = false;
      plan.querySelector("#plan-pay").focus();
      return;
    }
    if (!waitlist) {
      if (RM.checkout) window.location.href = RM.checkout;
      return;
    }
    form.reset();
    form.hidden = false;
    ok.hidden = true;
    form.origen_clic.value = origen;
    form.cif_consultado.value = cif || "";
    form.querySelector(".form-msg").textContent = "";
    waitlist.hidden = false;
    form.email.focus();
  }

  function close() {
    if (modal) modal.hidden = true;
  }

  async function pay(button) {
    const msg = plan.querySelector(".form-msg");
    button.disabled = true;
    msg.textContent = "Conectando con Stripe…";
    try {
      const resp = await fetch(`${RM.api}/api/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origen: current.origen, cif: current.cif }),
      });
      if ((resp.status === 404 || resp.status === 405) && RM.checkout) {
        window.location.href = RM.checkout; // despliegue con Payment Link (API Python)
        return;
      }
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data.url) {
        msg.textContent = RM.detail(data, "No se pudo iniciar el pago. Inténtalo de nuevo.");
        button.disabled = false;
        return;
      }
      window.location.href = data.url;
    } catch (_) {
      msg.textContent = "Sin conexión. Inténtalo de nuevo en unos segundos.";
      button.disabled = false;
    }
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-pro-origen]");
    if (trigger) {
      event.preventDefault();
      open(trigger.dataset.proOrigen, trigger.dataset.cif || RM.lastCif);
      return;
    }
    const payButton = event.target.closest("#plan-pay");
    if (payButton) {
      pay(payButton);
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
          msg.textContent = RM.detail(data, "No se pudo enviar. Inténtalo de nuevo.");
          return;
        }
        form.hidden = true;
        ok.textContent = data.mensaje || "Solicitud registrada. Te escribiremos por orden de solicitud.";
        ok.hidden = false;
      } catch (_) {
        msg.textContent = "Sin conexión. Inténtalo de nuevo en unos segundos.";
      }
    });
  }
  RM.openPro = open;
})();
