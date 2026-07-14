import clip
import numpy as np
import torch
from PIL import Image

from categories import CATEGORY_PROMPTS

_device = None
_model = None
_preprocess = None
_CATEGORY_TEXT_EMBEDDINGS: dict[str, list[float]] | None = None


def _get_model():
    global _device, _model, _preprocess
    if _model is None:
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _model, _preprocess = clip.load("ViT-B/32", device=_device)
    return _device, _model, _preprocess


def encode_pil_image(image: Image.Image) -> list[float]:
    device, model, preprocess = _get_model()
    tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        embedding = model.encode_image(tensor)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.cpu().numpy().flatten().tolist()


def encode_image(image_path: str) -> list[float]:
    return encode_pil_image(Image.open(image_path))


def encode_text(text: str) -> list[float]:
    device, model, _ = _get_model()
    tokens = clip.tokenize([text], truncate=True).to(device)
    with torch.no_grad():
        embedding = model.encode_text(tokens)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.cpu().numpy().flatten().tolist()


def cosine_similarity(vec_a: list[float] | None, vec_b: list[float] | None) -> float:
    if vec_a is None or vec_b is None:
        raise ValueError("Both vectors are required for cosine similarity")
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    return float(np.dot(a, b))


def _ensure_category_cache() -> dict[str, list[float]]:
    global _CATEGORY_TEXT_EMBEDDINGS
    if _CATEGORY_TEXT_EMBEDDINGS is None:
        _CATEGORY_TEXT_EMBEDDINGS = {
            category: encode_text(prompt) for category, prompt in CATEGORY_PROMPTS.items()
        }
    return _CATEGORY_TEXT_EMBEDDINGS


def predict_category(image: Image.Image) -> dict:
    image_vec = encode_pil_image(image)
    category_embeddings = _ensure_category_cache()
    scores = {
        category: cosine_similarity(image_vec, embedding)
        for category, embedding in category_embeddings.items()
    }
    predicted = max(scores, key=scores.get)
    return {
        "predicted": predicted,
        "confidence": scores[predicted],
        "all_scores": scores,
    }
