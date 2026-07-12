import clip
import torch
import numpy as np
from PIL import Image

from categories import CATEGORIES, CATEGORY_PROMPTS

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)


def encode_pil_image(image: Image.Image) -> list[float]:
    tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        embedding = model.encode_image(tensor)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.cpu().numpy().flatten().tolist()


def encode_image(image_path: str) -> list[float]:
    return encode_pil_image(Image.open(image_path))


def encode_text(text: str) -> list[float]:
    tokens = clip.tokenize([text], truncate=True).to(device)
    with torch.no_grad():
        embedding = model.encode_text(tokens)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding.cpu().numpy().flatten().tolist()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b))


def predict_category(image: Image.Image) -> dict:
    image_vec = encode_pil_image(image)
    scores = {
        category: cosine_similarity(image_vec, encode_text(prompt))
        for category, prompt in CATEGORY_PROMPTS.items()
    }
    predicted = max(scores, key=scores.get)
    return {
        "predicted": predicted,
        "confidence": scores[predicted],
        "all_scores": scores,
    }


def combined_match_score(
    text_to_image: float | None,
    image_to_image: float | None,
    found_text_to_lost_image: float | None,
) -> float:
    scores = [s for s in (text_to_image, image_to_image, found_text_to_lost_image) if s is not None]
    return sum(scores) / len(scores) if scores else 0.0


def match_breakdown(
    lost_text_embedding: list[float],
    lost_image_embedding: list[float] | None,
    found_text_embedding: list[float] | None,
    found_image_embedding: list[float] | None,
) -> tuple[float, dict[str, float | None]]:
    text_to_image = (
        cosine_similarity(lost_text_embedding, found_image_embedding)
        if found_image_embedding
        else None
    )
    image_to_image = (
        cosine_similarity(lost_image_embedding, found_image_embedding)
        if lost_image_embedding and found_image_embedding
        else None
    )
    found_text_to_lost_image = (
        cosine_similarity(found_text_embedding, lost_image_embedding)
        if found_text_embedding and lost_image_embedding
        else None
    )
    score = combined_match_score(text_to_image, image_to_image, found_text_to_lost_image)
    return score, {
        "text_to_image": text_to_image,
        "image_to_image": image_to_image,
        "found_text_to_lost_image": found_text_to_lost_image,
    }