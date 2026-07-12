from datetime import datetime
from io import BytesIO
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from categories import CATEGORIES
from clip_service import encode_pil_image, encode_text, match_breakdown, predict_category
from database import get_db
import models
import schemas

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def format_reported_by(email: str | None) -> str | None:
    if not email:
        return None
    local = email.split("@", 1)[0]
    parts = local.replace(".", " ").replace("_", " ").split()
    if not parts:
        return email
    if len(parts) == 1:
        return parts[0].capitalize()
    return f"{parts[0][0].upper()}. {parts[-1].capitalize()}"


@router.post("/predict-category", response_model=schemas.CategoryPredictionResponse)
async def predict_item_category(image: UploadFile = File(...)):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="A valid image file is required")

    try:
        pil_image = Image.open(image.file)
        result = predict_category(pil_image)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    return result


@router.post("/found", response_model=schemas.FoundItemResponse)
async def report_found_item(
    image: UploadFile = File(...),
    description: str | None = Form(None),
    category: str = Form(...),
    location: str | None = Form(None),
    date_found: str | None = Form(None),
    finder_email: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="A valid image file is required")

    try:
        image_bytes = await image.read()
        pil_image = Image.open(BytesIO(image_bytes))
        image_embedding = encode_pil_image(pil_image)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    filename = f"{uuid.uuid4()}{Path(image.filename or 'upload.jpg').suffix or '.jpg'}"
    (UPLOAD_DIR / filename).write_bytes(image_bytes)

    text_embedding = encode_text(description) if description else None
    now = datetime.now()

    item = models.FoundItem(
        description=description,
        category=category,
        location=location,
        date_found=date_found or now.strftime("%Y-%m-%d"),
        time_found=now.strftime("%I:%M %p").lstrip("0"),
        reported_by=format_reported_by(finder_email),
        finder_email=finder_email,
        image_path=filename,
        image_embedding=image_embedding,
        text_embedding=text_embedding,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "message": "Found item reported successfully",
        "category": item.category,
        "embedding_stored": True,
    }


@router.post("/lost", response_model=schemas.LostItemResponse)
async def report_lost_item(
    description: str = Form(...),
    category: str = Form(...),
    image: UploadFile | None = File(None),
    location: str | None = Form(None),
    date_lost: str | None = Form(None),
    email: str | None = Form(None),
    db: Session = Depends(get_db),
):
    search_all = category == "All"
    if not search_all and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")

    lost_image_embedding = None
    image_path = None

    if image and image.filename:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="A valid image file is required")
        try:
            image_bytes = await image.read()
            pil_image = Image.open(BytesIO(image_bytes))
            lost_image_embedding = encode_pil_image(pil_image)
            image_path = f"{uuid.uuid4()}{Path(image.filename or 'upload.jpg').suffix or '.jpg'}"
            (UPLOAD_DIR / image_path).write_bytes(image_bytes)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    lost_text_embedding = encode_text(description)
    lost_category = category if not search_all else "Other"

    lost_item = models.LostItem(
        description=description,
        category=lost_category,
        location=location,
        date_lost=date_lost,
        email=email,
        image_path=image_path,
        image_embedding=lost_image_embedding,
        text_embedding=lost_text_embedding,
    )
    db.add(lost_item)
    db.commit()

    query = db.query(models.FoundItem)
    if not search_all:
        query = query.filter(models.FoundItem.category == category)

    found_items = query.all()
    category_searched = "All categories" if search_all else category

    ranked_matches: list[dict] = []
    for found in found_items:
        score, breakdown = match_breakdown(
            lost_text_embedding=lost_text_embedding,
            lost_image_embedding=lost_image_embedding,
            found_text_embedding=found.text_embedding,
            found_image_embedding=found.image_embedding,
        )
        ranked_matches.append(
            {
                "id": found.id,
                "score": score,
                "category": found.category,
                "description": found.description,
                "location": found.location,
                "date_found": found.date_found,
                "time_found": found.time_found,
                "reported_by": found.reported_by,
                "image_url": f"/uploads/{found.image_path}" if found.image_path else None,
                "breakdown": breakdown,
            }
        )

    ranked_matches.sort(key=lambda match: match["score"], reverse=True)

    top_breakdown = (
        ranked_matches[0]["breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )

    matches = [
        {
            "id": match["id"],
            "score": match["score"],
            "category": match["category"],
            "description": match["description"],
            "location": match["location"],
            "date_found": match["date_found"],
            "time_found": match["time_found"],
            "reported_by": match["reported_by"],
            "image_url": match["image_url"],
        }
        for match in ranked_matches
    ]

    return {
        "matches": matches,
        "total_compared": len(found_items),
        "category_searched": category_searched,
        "scores_breakdown": top_breakdown,
    }
