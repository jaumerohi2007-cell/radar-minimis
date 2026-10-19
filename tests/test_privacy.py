import pytest

from radar_minimis.privacy import NifKind, classify, is_legal_entity, split_beneficiary


@pytest.mark.parametrize("nif", ["B12345674", "A11111119", "B00000000", "Q2826000H", "b-1234567-4", " B12345674 "])
def test_valid_legal_entities(nif):
    assert classify(nif) is NifKind.LEGAL_ENTITY
    assert is_legal_entity(nif)


@pytest.mark.parametrize("nif", ["12345678Z", "X1234567L", "K1234567L"])
def test_natural_persons_are_detected(nif):
    assert classify(nif) is NifKind.NATURAL_PERSON


@pytest.mark.parametrize("nif", ["B12345675", "Q2826000A", "A1111111A", "12345678A", "", "HOLA", "B1234567"])
def test_invalid_identifiers(nif):
    assert classify(nif) is NifKind.INVALID


def test_split_beneficiary():
    assert split_beneficiary("B12345674 EMPRESA DEMO, SL") == ("B12345674", "EMPRESA DEMO, SL")
    assert split_beneficiary("SIN NIF SA") == (None, "SIN NIF SA")
    assert split_beneficiary("") == (None, "")
