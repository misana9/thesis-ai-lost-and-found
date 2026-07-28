import clip
import numpy as np
import torch
from PIL import Image

from categories import CATEGORY_PROMPTS

_device = None
_model = None
_preprocess = None
_cat_embeds = None


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
        emb = model.encode_image(tensor)
        emb /= emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy().flatten().tolist()


def encode_image(image_path: str) -> list[float]:
    return encode_pil_image(Image.open(image_path))


def encode_text(text: str) -> list[float]:
    device, model, _ = _get_model()
    tokens = clip.tokenize([text], truncate=True).to(device)
    with torch.no_grad():
        emb = model.encode_text(tokens)
        emb /= emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy().flatten().tolist()


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if a is None or b is None:
        raise ValueError("Both vectors are required for cosine similarity")
    return float(np.dot(np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)))


def _load_cat_embeds() -> dict[str, list[float]]:
    global _cat_embeds
    if _cat_embeds is None:
        _cat_embeds = {
            cat: encode_text(prompt) for cat, prompt in CATEGORY_PROMPTS.items()
        }
    return _cat_embeds


def predict_category(image: Image.Image) -> dict:
    img_vec = encode_pil_image(image)
    scores = {
        cat: cosine_similarity(img_vec, emb)
        for cat, emb in _load_cat_embeds().items()
    }
    predicted = max(scores, key=scores.get)
    return {
        "predicted": predicted,
        "confidence": scores[predicted],
        "all_scores": scores,
    }
