"""Shared model contract without network downloads."""
import os
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


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("EMBED_BACKEND", "tensorflow")
    with pytest.raises(ValueError):
        model.embed_texts(["test"])


def test_onnx_backend_mean_pools_without_padding_and_normalizes(monkeypatch):
    """Fake tokenizer/session: padding positions must not change the pooled vector."""
    np = pytest.importorskip("numpy")
    monkeypatch.setenv("EMBED_BACKEND", "onnx")

    class Encoding:
        def __init__(self, n_real, length):
            self.ids = [1] * n_real + [0] * (length - n_real)
            self.attention_mask = [1] * n_real + [0] * (length - n_real)
            self.type_ids = [0] * length

    tokenizer = Mock()
    tokenizer.encode_batch.return_value = [Encoding(2, 3), Encoding(3, 3)]
    session = Mock()
    session.get_inputs.return_value = [Mock(), Mock()]
    session.get_inputs.return_value[0].name = "input_ids"
    session.get_inputs.return_value[1].name = "attention_mask"
    tokens = np.zeros((2, 3, 384), dtype=np.float32)
    tokens[0, 0, 0], tokens[0, 1, 0], tokens[0, 2, 1] = 3.0, 1.0, 100.0  # [0,2] is padding
    tokens[1, :, 1] = 4.0
    session.run.return_value = [tokens]
    with patch.object(model, "_load_onnx", return_value=(tokenizer, session)):
        first, second = model.embed_texts(["short", "longer text"])
    assert len(first) == 384
    assert first[0] == pytest.approx(1.0) and first[1] == 0.0  # padding ignored, normalized
    assert second[1] == pytest.approx(1.0)
    fed = session.run.call_args.args[1]
    assert set(fed) == {"input_ids", "attention_mask"}  # only inputs the model declares


@pytest.mark.skipif(os.environ.get("RUN_EMBED_PARITY") != "1",
                    reason="set RUN_EMBED_PARITY=1 (downloads the model; needs torch and onnxruntime)")
def test_onnx_matches_sentence_transformers(monkeypatch):
    """Both backends must give the same vectors, or search quietly degrades."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("onnxruntime")
    texts = [
        "How should a rep qualify an enterprise opportunity?",
        "MEDDICC",
        "Territory planning for SMB, commercial and ENTERPRISE segments!",
        # Longer than 256 tokens, so truncation must match too.
        " ".join(["Discovery calls should confirm pain, budget, authority and timeline."] * 60),
    ]
    vectors = {}
    for name in ("sentence-transformers", "onnx"):
        monkeypatch.setenv("EMBED_BACKEND", name)
        vectors[name] = np.array(model.embed_texts(texts))
        single = np.array(model.embed_texts(texts[:1]))  # no padding in a batch of one
        assert np.dot(single[0], vectors[name][0]) > 0.9999
    cosine = (vectors["sentence-transformers"] * vectors["onnx"]).sum(axis=1)
    assert cosine.min() >= 0.999, cosine
