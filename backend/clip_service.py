import logging
import os
from pathlib import Path

import clip
import numpy as np
import torch
from PIL import Image

from categories import CATEGORY_PROMPTS, SERIAL_LIKELY_CATEGORIES

logger = logging.getLogger("amalost.clip")

_device = None
_model = None
_preprocess = None
_cat_names: list[str] | None = None
_cat_matrix: np.ndarray | None = None

_CPU_THREADS = max(1, int(os.environ.get("OMP_NUM_THREADS", "4")))


def _configure_torch_threads() -> None:
    torch.set_num_threads(_CPU_THREADS)
    torch.set_num_interop_threads(1)


def _load_finetuned_weights(model) -> None:
    try:
        from config import settings
    except Exception:
        return
    path = getattr(settings, "clip_ft_checkpoint", None)
    if not path:
        return
    ckpt_path = Path(path)
    if not ckpt_path.is_file():
        logger.warning("CLIP fine-tune checkpoint not found: %s", ckpt_path)
        return
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
    model.load_state_dict(state)
    logger.info("Loaded fine-tuned CLIP weights from %s", ckpt_path)


def _get_model():
    global _device, _model, _preprocess
    if _model is None:
        _configure_torch_threads()
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _model, _preprocess = clip.load("ViT-B/32", device=_device)
        _load_finetuned_weights(_model)
        _model.eval()
        logger.info("CLIP ViT-B/32 ready on %s (threads=%s)", _device, _CPU_THREADS)
    return _device, _model, _preprocess


def encode_pil_image(image: Image.Image) -> list[float]:
    device, model, preprocess = _get_model()
    tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = model.encode_image(tensor)
        emb /= emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy().astype(np.float32).flatten().tolist()


def encode_image(image_path: str) -> list[float]:
    return encode_pil_image(Image.open(image_path))


def encode_text(text: str) -> list[float]:
    return encode_texts([text])[0]


def encode_texts(texts: list[str]) -> list[list[float]]:
    device, model, _ = _get_model()
    tokens = clip.tokenize(texts, truncate=True).to(device)
    with torch.no_grad():
        emb = model.encode_text(tokens)
        emb /= emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy().astype(np.float32).tolist()


def cosine_similarity(a: list[float] | np.ndarray | None, b: list[float] | np.ndarray | None) -> float:
    if a is None or b is None:
        raise ValueError("Both vectors are required for cosine similarity")
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    return float(np.dot(va, vb))


def as_vec(value) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32)


def _load_cat_matrix() -> tuple[list[str], np.ndarray]:
    global _cat_names, _cat_matrix
    if _cat_names is None or _cat_matrix is None:
        _cat_names = list(CATEGORY_PROMPTS.keys())
        prompts = [CATEGORY_PROMPTS[name] for name in _cat_names]
        _cat_matrix = np.asarray(encode_texts(prompts), dtype=np.float32)
    return _cat_names, _cat_matrix


def predict_category(image: Image.Image) -> dict:
    img_vec = np.asarray(encode_pil_image(image), dtype=np.float32)
    names, matrix = _load_cat_matrix()
    scores_arr = matrix @ img_vec
    scores = {name: float(scores_arr[i]) for i, name in enumerate(names)}
    predicted = names[int(scores_arr.argmax())]
    serial_likely = predicted in SERIAL_LIKELY_CATEGORIES
    return {
        "predicted": predicted,
        "confidence": scores[predicted],
        "all_scores": scores,
        "serial_likely": serial_likely,
        "high_value_suggested": serial_likely,
    }
