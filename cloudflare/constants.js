// GENERADO por `uv run python data_engine.py cloudflare-constants` desde radar_minimis (Python).
// No editar a mano: tests/test_cloudflare.py comprueba que coincide con el motor Python.
export const VERSION = "0.2.0";
export const ATTRIBUTION = "Origen de los datos: Intervención General de la Administración del Estado (BDNS / SNPSAP)";
export const DISCLAIMER = "Radar Minimis no es un servicio oficial ni está patrocinado por la Intervención General de la Administración del Estado. Información orientativa basada en datos públicos dinámicos.";
export const SINGLE_UNDERTAKING_NOTICE = "«Única empresa» (art. 2.2 del Reg. (UE) 2023/2831): el tope se comparte entre todas las empresas que tengan entre sí al menos uno de estos vínculos: a) una posee la mayoría de los derechos de voto de los socios de otra; b) una puede nombrar o revocar a la mayoría del órgano de administración, dirección o supervisión de otra; c) una puede ejercer una influencia dominante sobre otra por contrato o por sus estatutos; d) una, socia de otra, controla por sí sola la mayoría de los derechos de voto por acuerdo con otros socios. También cuentan estos vínculos a través de otras empresas. Si tu empresa tiene matriz o filiales, suma sus CIF: el margen de un solo CIF puede ser mayor que el real.";
export const CRITERIO_ACUMULACION = "Criterio prudente: el art. 5.1 del Reg. (UE) 2023/2831 permite acumular ayudas generales y SIEG sin fijar un tope conjunto expreso; la calculadora limita la suma general + SIEG a 750.000 € para no sobrestimar el margen.";
export const BASE_WARNINGS = ["Solo incluye ayudas registradas en la BDNS; las concesiones recientes pueden tardar en aparecer.", "Informe orientativo, no constituye asesoramiento jurídico."];
export const WARN_SINGLE_CIF = "Calculado para 1 CIF: si hay empresas vinculadas, añádelas (ver «única empresa»).";
export const WARN_EXCEEDED = "ATENCIÓN: las ayudas registradas superan al menos uno de los topes aplicables.";
export const WARN_UNKNOWN = "{n} concesión(es) con reglamento no reconocido se han sumado al tope general.";
export const WARN_LEGACY = "Incluye ayudas del Reg. (UE) 1407/2013 concedidas dentro del período de tres años.";
export const WARN_PESCA = "Pesca: se computan el ejercicio en curso y los dos anteriores (ejercicio = año natural).";
export const SEMAFORO_AMBAR = 0.5;
export const SEMAFORO_ROJO = 0.85;
export const PESCA_BASE_CEILING_EUR = 30000.0;
export const RULES = {"general": {"tope": 300000.0, "ventana": "tres_anos_moviles", "base": "Reg. (UE) 2023/2831, art. 3.2"}, "sieg": {"tope": 750000.0, "ventana": "tres_anos_moviles", "base": "Reg. (UE) 2023/2832, art. 3.2"}, "agricola": {"tope": 50000.0, "ventana": "tres_anos_moviles", "base": "Reg. (UE) 1408/2013, art. 3.2 (redacción del Reg. 2024/3118)"}, "pesca": {"tope": 40000.0, "ventana": "ejercicio_en_curso_y_dos_anteriores", "base": "Reg. (UE) 717/2014, art. 3.2 bis (Reg. 2023/2391) y RD 1139/2024, art. 3.2"}};
export const ORIGENES = ["informe_pdf", "cartera_lote", "grupo_societario", "alertas_cartera"];
export const EVENTOS_CLIENTE = ["informe_generado", "informe_impreso", "demo_asesorias_vista", "modal_informe_pdf", "modal_cartera_lote", "modal_grupo_societario", "modal_alertas_cartera"];
export const CONSENTIMIENTO_VERSION = "lista-espera-v1-2026-10-19";
export const EARLY_ACCESS_TITLE = "Acceso Asesorías Pro";
export const EARLY_ACCESS_COPY = "Monitoriza hasta 100 CIFs en automático y genera informes de minimis en 1 clic. Estamos activando cuentas por orden de solicitud con un 50% de descuento vitalicio (19 €/mes). Déjanos tu email profesional y el número aproximado de empresas que gestionas.";
export const MAX_NUM_CIFS = 100000;
export const PLAN = {"codigo": "pro_100", "nombre": "Radar Minimis — Plan Asesorías Pro", "importe_cent": 1900, "precio": "19,00 €/mes", "max_cifs": 100, "max_vinculadas": 3};
