"""Shared model contract without network downloads."""
from unittest.mock import Mock, patch

import pytest

from embed import model


def test_shared_embeddings_are_normalized_and_empty_input_does_not_load():
    fake = Mock()
    fake.encode.return_value = [[1.0] + [0.0] * 383]
    with patch.object(model, "_load_model", return_value=fake) as load:
        assert model.embed_texts([]) == []
        load.assert_not_called()
        vectors = model.embed_texts(["Synthetic claim"])
    assert len(vectors[0]) == 384
    fake.encode.assert_called_once_with(["Synthetic claim"], normalize_embeddings=True)


def test_model_override_cannot_silently_mismatch_database(monkeypatch):
    monkeypatch.setenv("EMBED_MODEL", "other-model")
    with pytest.raises(ValueError):
        model.embed_texts(["test"])
