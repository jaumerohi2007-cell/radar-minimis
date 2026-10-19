"""Identificadores fiscales españoles: validación y clasificación.

Regla de producto, derivada del aviso legal de la BDNS: los documentos con datos
personales solo pueden reutilizarse para controlar la actuación de los gestores
públicos o con fines históricos, estadísticos o científicos, previa disociación.
Por eso todo NIF de persona física se descarta en la ingesta y se rechaza en la API.
"""

from __future__ import annotations

import re
from enum import StrEnum

DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
CIF_CONTROL_LETTERS = "JABCDEFGHI"

_CIF_RE = re.compile(r"^([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])$")
_DNI_RE = re.compile(r"^(\d{8})([A-Z])$")
_NIE_RE = re.compile(r"^([XYZ])(\d{7})([A-Z])$")
_KLM_RE = re.compile(r"^([KLM])(\d{7})([A-Z])$")

# Tipo de dígito de control según la letra de organización del CIF.
_CIF_LETTER_CONTROL = set("NPQRSW")
_CIF_DIGIT_CONTROL = set("ABEH")


class NifKind(StrEnum):
    LEGAL_ENTITY = "persona_juridica"
    NATURAL_PERSON = "persona_fisica"
    INVALID = "invalido"


def normalize(value: str) -> str:
    return re.sub(r"[\s.\-/]", "", value or "").upper()


def _cif_control_index(digits: str) -> int:
    total = 0
    for position, char in enumerate(digits, start=1):
        n = int(char)
        if position % 2:  # posiciones impares: se duplican y se suman sus cifras
            n *= 2
            n = n // 10 + n % 10
        total += n
    return (10 - total % 10) % 10


def cif_with_control(letter: str, digits: str) -> str:
    """Construye un CIF con su dígito de control (útil para datos de demostración y tests)."""
    if letter not in "ABCDEFGHJNPQRSUVW" or len(digits) != 7 or not digits.isdigit():
        raise ValueError("letra de organización o dígitos no válidos")
    idx = _cif_control_index(digits)
    return f"{letter}{digits}{CIF_CONTROL_LETTERS[idx] if letter in _CIF_LETTER_CONTROL else idx}"


def classify(value: str) -> NifKind:
    nif = normalize(value)
    if m := _CIF_RE.match(nif):
        letter, digits, control = m.groups()
        idx = _cif_control_index(digits)
        as_digit, as_letter = str(idx), CIF_CONTROL_LETTERS[idx]
        if letter in _CIF_LETTER_CONTROL:
            ok = control == as_letter
        elif letter in _CIF_DIGIT_CONTROL:
            ok = control == as_digit
        else:
            ok = control in (as_digit, as_letter)
        return NifKind.LEGAL_ENTITY if ok else NifKind.INVALID
    if m := _DNI_RE.match(nif):
        number, letter = m.groups()
        return NifKind.NATURAL_PERSON if DNI_LETTERS[int(number) % 23] == letter else NifKind.INVALID
    if m := _NIE_RE.match(nif):
        prefix, number, letter = m.groups()
        n = int(str("XYZ".index(prefix)) + number)
        return NifKind.NATURAL_PERSON if DNI_LETTERS[n % 23] == letter else NifKind.INVALID
    if m := _KLM_RE.match(nif):
        _, number, letter = m.groups()
        return NifKind.NATURAL_PERSON if DNI_LETTERS[int(number) % 23] == letter else NifKind.INVALID
    return NifKind.INVALID


def is_legal_entity(value: str) -> bool:
    return classify(value) is NifKind.LEGAL_ENTITY


def split_beneficiary(text: str) -> tuple[str | None, str]:
    """La BDNS publica el beneficiario como "B16403180 RAZON SOCIAL, SL": separa NIF y nombre."""
    text = (text or "").strip()
    head, _, rest = text.partition(" ")
    if classify(head) is not NifKind.INVALID:
        return normalize(head), rest.strip()
    return None, text
