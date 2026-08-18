"""Tests de normalización del destinatario."""

import pytest

from wacloud.recipient import digits_only, normalize_recipient, recipient_block


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+57 322 543 2100", "573225432100"),
        ("57-322-543-2100", "573225432100"),
        ("(57) 3225432100", "573225432100"),
        ("573225432100", "573225432100"),
    ],
)
def test_strips_formatting(raw, expected):
    assert normalize_recipient(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "+", None])
def test_rejects_input_without_digits(raw):
    """Un ``to`` vacío produce un 400 genérico de Meta que no dice qué mensaje falló."""
    with pytest.raises(ValueError, match="no contiene dígitos"):
        normalize_recipient(raw)


def test_rejects_too_short():
    with pytest.raises(ValueError, match="mínimo"):
        normalize_recipient("123")


def test_rejects_longer_than_e164():
    with pytest.raises(ValueError, match=r"E\.164"):
        normalize_recipient("1" * 16)


def test_digits_only_does_not_validate():
    """``digits_only`` es la primitiva sin opinión; validar es cosa de normalize."""
    assert digits_only("abc") == ""


def test_recipient_block_shape():
    assert recipient_block("+57 322 543 2100") == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "573225432100",
    }
