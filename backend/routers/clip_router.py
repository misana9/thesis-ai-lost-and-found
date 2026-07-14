from datetime import datetime
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from categories import CATEGORIES
from clip_service import cosine_similarity, encode_pil_image, encode_text, predict_category
from database import get_db
from image_utils import read_and_sanitize_image
from matching import compute_match
import models
import oauth2
import schemas

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEDUP_THRESHOLD = 0.98


def format_reported_by(email: str | None, full_name: str | None = None) -> str | None:
    if full_name:
        parts = full_name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0].upper()}. {parts[-1].capitalize()}"
        return full_name
    if not email:
        return None
    local = email.split("@", 1)[0]
    parts = local.replace(".", " ").replace("_", " ").split()
    if not parts:
        return email
    if len(parts) == 1:
        return parts[0].capitalize()
    return f"{parts[0][0].upper()}. {parts[-1].capitalize()}"


def embedding_list(value) -> list[float] | None:
    if value is None:
        return None
    return list(value)


def find_near_duplicate(db: Session, image_embedding: list[float]) -> models.FoundItem | None:
    candidates = (
        db.query(models.FoundItem)
        .filter(models.FoundItem.status == "available")
        .filter(models.FoundItem.image_embedding.isnot(None))
        .all()
    )
    for item in candidates:
        existing = embedding_list(item.image_embedding)
        if existing is None:
            continue
        if cosine_similarity(image_embedding, existing) >= DEDUP_THRESHOLD:
            return item
    return None


@router.post("/predict-category", response_model=schemas.CategoryPredictionResponse)
async def predict_item_category(image: UploadFile = File(...)):
    try:
        pil_image, _ = await read_and_sanitize_image(image)
        return predict_category(pil_image)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image")


@router.post("/found", response_model=schemas.FoundItemResponse)
async def report_found_item(
    image: UploadFile = File(...),
    description: str | None = Form(None),
    category: str = Form(...),
    location: str | None = Form(None),
    date_found: str | None = Form(None),
    finder_email: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.Users | None = Depends(oauth2.get_optional_user),
):
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")

    try:
        pil_image, jpeg_bytes = await read_and_sanitize_image(image)
        image_embedding = encode_pil_image(pil_image)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    duplicate = find_near_duplicate(db, image_embedding)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A nearly identical item was already reported (id={duplicate.id})",
        )

    filename = f"{uuid.uuid4()}.jpg"
    (UPLOAD_DIR / filename).write_bytes(jpeg_bytes)

    text_embedding = encode_text(description) if description else None
    now = datetime.now()

    email = finder_email
    reported_by = format_reported_by(email)
    finder_user_id = None
    if current_user:
        email = current_user.email
        reported_by = format_reported_by(current_user.email, current_user.full_name)
        finder_user_id = current_user.id

    item = models.FoundItem(
        description=description,
        category=category,
        location=location,
        date_found=date_found or now.strftime("%Y-%m-%d"),
        time_found=now.strftime("%I:%M %p").lstrip("0"),
        reported_by=reported_by,
        finder_email=email,
        finder_user_id=finder_user_id,
        image_path=filename,
        image_embedding=image_embedding,
        text_embedding=text_embedding,
        status="available",
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
    original_category: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.Users | None = Depends(oauth2.get_optional_user),
):
    search_all = category == "All"
    preferred_category = original_category if search_all and original_category else category
    if preferred_category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}",
        )

    lost_image_embedding = None
    image_path = None

    if image and image.filename:
        try:
            pil_image, jpeg_bytes = await read_and_sanitize_image(image)
            lost_image_embedding = encode_pil_image(pil_image)
            image_path = f"{uuid.uuid4()}.jpg"
            (UPLOAD_DIR / image_path).write_bytes(jpeg_bytes)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    lost_text_embedding = encode_text(description)
    lost_category = preferred_category

    owner_email = email
    owner_user_id = None
    if current_user:
        owner_email = current_user.email
        owner_user_id = current_user.id

    lost_item = models.LostItem(
        description=description,
        category=lost_category,
        location=location,
        date_lost=date_lost,
        email=owner_email,
        owner_user_id=owner_user_id,
        image_path=image_path,
        image_embedding=lost_image_embedding,
        text_embedding=lost_text_embedding,
        status="open",
    )
    db.add(lost_item)
    db.commit()
    db.refresh(lost_item)

    # Soft category preference via scoring multiplier — no hard SQL filter.
    # Prefer available items; use pgvector cosine distance when a lost image exists.
    query = db.query(models.FoundItem).filter(models.FoundItem.status == "available")
    if lost_image_embedding is not None:
        query = query.order_by(models.FoundItem.image_embedding.cosine_distance(lost_image_embedding))
    found_items = query.all()
    category_searched = "All categories" if search_all else category

    ranked_matches: list[dict] = []
    for found in found_items:
        found_image = embedding_list(found.image_embedding)
        found_text = embedding_list(found.text_embedding)
        if found_image is None:
            continue

        text_to_image = cosine_similarity(lost_text_embedding, found_image)
        image_to_image = (
            cosine_similarity(lost_image_embedding, found_image)
            if lost_image_embedding is not None
            else None
        )
        found_text_to_lost_image = (
            cosine_similarity(found_text, lost_image_embedding)
            if (found_text is not None and lost_image_embedding is not None)
            else None
        )

        # Soft category preference via scoring — never hard-filter candidates.
        compare_category = preferred_category

        final_score, tier, same_category, scores_breakdown = compute_match(
            text_to_image=text_to_image,
            image_to_image=image_to_image,
            found_text_to_lost_image=found_text_to_lost_image,
            lost_category=compare_category,
            found_category=found.category,
            lost_location=location,
            found_location=found.location,
            lost_date=date_lost,
            found_date=found.date_found,
        )

        if tier is None:
            continue

        ranked_matches.append(
            {
                "id": found.id,
                "score": final_score,
                "category": found.category,
                "description": found.description,
                "location": found.location,
                "date_found": found.date_found,
                "time_found": found.time_found,
                "reported_by": found.reported_by,
                "image_url": f"/uploads/{found.image_path}" if found.image_path else None,
                "same_category": same_category,
                "tier": tier,
                "scores_breakdown": scores_breakdown,
            }
        )

    ranked_matches.sort(key=lambda match: match["score"], reverse=True)

    top_breakdown = (
        ranked_matches[0]["scores_breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )

    return {
        "id": lost_item.id,
        "matches": ranked_matches,
        "total_compared": len(found_items),
        "category_searched": category_searched,
        "scores_breakdown": top_breakdown,
    }


@router.post("/claim", response_model=schemas.ClaimResponse)
async def claim_item(
    body: schemas.ClaimRequest,
    db: Session = Depends(get_db),
    current_user: models.Users | None = Depends(oauth2.get_optional_user),
):
    found = db.query(models.FoundItem).filter(models.FoundItem.id == body.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == body.lost_item_id).first()

    if not found or not lost:
        raise HTTPException(status_code=404, detail="Found or lost item not found")
    if found.status != "available":
        raise HTTPException(status_code=409, detail="This found item is no longer available")
    if lost.status == "claimed":
        raise HTTPException(status_code=409, detail="This lost report was already claimed")

    email = body.email or lost.email
    user_id = None
    if current_user:
        email = current_user.email
        user_id = current_user.id

    notify_message = (
        f"Claim submitted for found item {found.id}. "
        f"Owner ({email or 'unknown'}) and finder ({found.finder_email or found.reported_by or 'unknown'}) "
        f"would be emailed to arrange pickup at Library Information Desk."
    )

    claim = models.Claim(
        found_item_id=found.id,
        lost_item_id=lost.id,
        claimed_by_email=email,
        claimed_by_user_id=user_id,
        status="pending",
        notify_message=notify_message,
    )
    found.status = "claimed"
    found.claimed_by_lost_id = lost.id
    lost.status = "claimed"

    db.add(claim)
    db.commit()
    db.refresh(claim)

    return {
        "id": claim.id,
        "status": claim.status,
        "message": "Claim recorded. We'll notify the finder by email.",
        "notify_message": notify_message,
    }


@router.get("/admin/queue", response_model=schemas.AdminQueueResponse)
async def admin_queue(
    db: Session = Depends(get_db),
    _admin: models.Users = Depends(oauth2.get_admin_user),
):
    found_items = db.query(models.FoundItem).order_by(models.FoundItem.created_at.desc()).limit(100).all()
    lost_items = db.query(models.LostItem).order_by(models.LostItem.created_at.desc()).limit(100).all()
    claims = db.query(models.Claim).order_by(models.Claim.created_at.desc()).limit(100).all()

    return {
        "found_items": [
            {
                "id": item.id,
                "description": item.description,
                "category": item.category,
                "location": item.location,
                "date_found": item.date_found,
                "time_found": item.time_found,
                "reported_by": item.reported_by,
                "finder_email": item.finder_email,
                "image_url": f"/uploads/{item.image_path}" if item.image_path else None,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in found_items
        ],
        "lost_items": [
            {
                "id": item.id,
                "description": item.description,
                "category": item.category,
                "location": item.location,
                "date_lost": item.date_lost,
                "email": item.email,
                "image_url": f"/uploads/{item.image_path}" if item.image_path else None,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in lost_items
        ],
        "claims": [
            {
                "id": claim.id,
                "found_item_id": claim.found_item_id,
                "lost_item_id": claim.lost_item_id,
                "claimed_by_email": claim.claimed_by_email,
                "status": claim.status,
                "notify_message": claim.notify_message,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
            for claim in claims
        ],
    }


# Public read-only queue for demo admin UI without forcing admin seed during thesis demos.
@router.get("/queue", response_model=schemas.AdminQueueResponse)
async def public_queue(db: Session = Depends(get_db)):
    found_items = db.query(models.FoundItem).order_by(models.FoundItem.created_at.desc()).limit(50).all()
    lost_items = db.query(models.LostItem).order_by(models.LostItem.created_at.desc()).limit(50).all()
    claims = db.query(models.Claim).order_by(models.Claim.created_at.desc()).limit(50).all()

    return {
        "found_items": [
            {
                "id": item.id,
                "description": item.description,
                "category": item.category,
                "location": item.location,
                "date_found": item.date_found,
                "time_found": item.time_found,
                "reported_by": item.reported_by,
                "finder_email": item.finder_email,
                "image_url": f"/uploads/{item.image_path}" if item.image_path else None,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in found_items
        ],
        "lost_items": [
            {
                "id": item.id,
                "description": item.description,
                "category": item.category,
                "location": item.location,
                "date_lost": item.date_lost,
                "email": item.email,
                "image_url": f"/uploads/{item.image_path}" if item.image_path else None,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in lost_items
        ],
        "claims": [
            {
                "id": claim.id,
                "found_item_id": claim.found_item_id,
                "lost_item_id": claim.lost_item_id,
                "claimed_by_email": claim.claimed_by_email,
                "status": claim.status,
                "notify_message": claim.notify_message,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
            for claim in claims
        ],
    }
