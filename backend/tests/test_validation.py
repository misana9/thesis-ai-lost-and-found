from validation import validate_item_description
import pytest


def test_rejects_empty():
    with pytest.raises(ValueError, match="short description"):
        validate_item_description("")


def test_rejects_vague():
    with pytest.raises(ValueError, match="vague"):
        validate_item_description("thing stuff")


def test_rejects_too_short():
    with pytest.raises(ValueError, match="too short"):
        validate_item_description("phone")


def test_accepts_specific():
    assert validate_item_description("black Casio calculator") == "black Casio calculator"
