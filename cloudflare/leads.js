// Validación de la lista de espera: mismas reglas y mensajes que radar_minimis/leads.py.
import * as K from "./constants.js";
import { LEGAL_ENTITY, classifyNif, normalize } from "./core.js";

const EMAIL_RE = /^[^@\s'"<>]{1,64}@[^@\s'"<>]+\.[^@\s'"<>]{2,}$/;

export class LeadError extends Error {}

/** Devuelve null si el envío es de un bot (campo trampa relleno); lanza LeadError si no es válido. */
export function validateLead(payload) {
  if (String(payload.web ?? "").trim()) return null;
  const email = String(payload.email ?? "").trim().toLowerCase();
  if (email.length > 254 || !EMAIL_RE.test(email)) throw new LeadError("Introduce un email profesional válido.");
  const raw = payload.num_cifs_estimados;
  if (typeof raw === "boolean" || !/^\d+$/.test(String(raw ?? "").trim()))
    throw new LeadError("Indica cuántas empresas gestionas aproximadamente.");
  const num = Number(String(raw).trim());
  if (num < 1 || num > K.MAX_NUM_CIFS) throw new LeadError(`El número de empresas debe estar entre 1 y ${K.MAX_NUM_CIFS}.`);
  if (!K.ORIGENES.includes(payload.origen_clic)) throw new LeadError("Origen de la solicitud no válido.");
  if (payload.consentimiento !== true) throw new LeadError("Necesitamos tu consentimiento para guardar el email.");
  const cif = normalize(payload.cif_consultado);
  // Nunca se guarda un DNI/NIE: solo CIF de personas jurídicas válidos.
  return { email, num_cifs_estimados: num, cif_consultado: cif && classifyNif(cif) === LEGAL_ENTITY ? cif : null, origen_clic: payload.origen_clic };
}
