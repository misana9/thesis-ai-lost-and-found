from datetime import datetime
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from categories import CATEGORIES
from clip_service import cosine_similarity, encode_pil_image, encode_text, predict_category
from database import get_db
from email_service import (
    notify_claim_to_finder,
    notify_claim_to_owner,
    notify_match_to_finder,
    notify_match_to_owner,
)
from image_utils import read_and_sanitize_image
from matching import compute_match
import models
import oauth2
import schemas

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEDUP_THRESHOLD = 0.98


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def resolve_uploader_email(
    form_email: str | None,
    current_user: models.Users | None,
    *,
    required: bool = True,
) -> str | None:
    """Prefer authenticated user email; fall back to form. Require for ownership tracking."""
    email = normalize_email(current_user.email if current_user else None) or normalize_email(form_email)
    if required and not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required so we can notify you about matches and claims",
        )
    return email


def emails_match(a: str | None, b: str | None) -> bool:
    left = normalize_email(a)
    right = normalize_email(b)
    return bool(left and right and left == right)


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


def score_lost_against_found(
    *,
    lost_text_embedding: list[float],
    lost_image_embedding: list[float] | None,
    lost_category: str,
    lost_location: str | None,
    lost_date: str | None,
    found: models.FoundItem,
) -> dict | None:
    found_image = embedding_list(found.image_embedding)
    found_text = embedding_list(found.text_embedding)
    if found_image is None:
        return None

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

    final_score, tier, same_category, scores_breakdown = compute_match(
        text_to_image=text_to_image,
        image_to_image=image_to_image,
        found_text_to_lost_image=found_text_to_lost_image,
        lost_category=lost_category,
        found_category=found.category,
        lost_location=lost_location,
        found_location=found.location,
        lost_date=lost_date,
        found_date=found.date_found,
    )
    if tier is None:
        return None

    return {
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
        "finder_email": found.finder_email,
    }


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

    email = resolve_uploader_email(finder_email, current_user)

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

    reported_by = format_reported_by(
        email,
        current_user.full_name if current_user else None,
    )
    finder_user_id = current_user.id if current_user else None

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

    # Reverse match: notify owners of open lost reports that may match this find.
    # Skip any lost report filed by the same email (self-match).
    open_lost = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .filter(models.LostItem.text_embedding.isnot(None))
        .all()
    )
    reverse_hits: list[dict] = []
    for lost in open_lost:
        if emails_match(lost.email, email):
            continue
        lost_text = embedding_list(lost.text_embedding)
        if lost_text is None:
            continue
        hit = score_lost_against_found(
            lost_text_embedding=lost_text,
            lost_image_embedding=embedding_list(lost.image_embedding),
            lost_category=lost.category,
            lost_location=lost.location,
            lost_date=lost.date_lost,
            found=item,
        )
        if hit is None:
            continue
        reverse_hits.append({**hit, "lost_id": lost.id, "owner_email": lost.email})

    reverse_hits.sort(key=lambda m: m["score"], reverse=True)
    notified = 0
    notified_finders: set[str] = set()
    for hit in reverse_hits:
        owner = normalize_email(hit.get("owner_email"))
        if not owner:
            continue
        notify_match_to_owner(
            owner_email=owner,
            category=hit["category"],
            match_count=1,
            top_score=hit["score"],
        )
        notified += 1
        if email and email not in notified_finders:
            notify_match_to_finder(
                finder_email=email,
                category=item.category,
                location=item.location,
            )
            notified_finders.add(email)

    message = "Found item reported successfully"
    if reverse_hits:
        message = (
            f"Found item reported successfully. "
            f"Notified {notified} owner(s) of possible matching lost report(s)."
        )

    return {
        "id": item.id,
        "message": message,
        "category": item.category,
        "embedding_stored": True,
        "matches_notified": notified,
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

    owner_email = resolve_uploader_email(email, current_user)

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
    owner_user_id = current_user.id if current_user else None

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
        # Never surface the uploader's own found reports as matches.
        if emails_match(found.finder_email, owner_email):
            continue

        match = score_lost_against_found(
            lost_text_embedding=lost_text_embedding,
            lost_image_embedding=lost_image_embedding,
            lost_category=preferred_category,
            lost_location=location,
            lost_date=date_lost,
            found=found,
        )
        if match is None:
            continue
        ranked_matches.append({k: v for k, v in match.items() if k != "finder_email"})

    ranked_matches.sort(key=lambda match: match["score"], reverse=True)
    for index, match in enumerate(ranked_matches, start=1):
        match["rank"] = index

    if ranked_matches and owner_email:
        notify_match_to_owner(
            owner_email=owner_email,
            category=lost_category,
            match_count=len(ranked_matches),
            top_score=ranked_matches[0]["score"],
        )
        notified_finders: set[str] = set()
        for match in ranked_matches:
            # Re-fetch finder email from DB row for notification.
            found_row = next((f for f in found_items if f.id == match["id"]), None)
            finder = normalize_email(found_row.finder_email if found_row else None)
            if finder and finder not in notified_finders:
                notify_match_to_finder(
                    finder_email=finder,
                    category=match["category"],
                    location=match.get("location"),
                )
                notified_finders.add(finder)

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
        "lost_image_url": f"/uploads/{lost_item.image_path}" if lost_item.image_path else None,
        "lost_description": lost_item.description,
        "lost_category": lost_item.category,
        "lost_location": lost_item.location,
        "lost_date": lost_item.date_lost,
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

    email = resolve_uploader_email(body.email or lost.email, current_user)
    if emails_match(email, found.finder_email):
        raise HTTPException(
            status_code=400,
            detail="You cannot claim an item you reported found yourself",
        )

    user_id = current_user.id if current_user else None
    finder_email = normalize_email(found.finder_email)

    owner_result = notify_claim_to_owner(
        owner_email=email,
        category=found.category,
        finder_email=finder_email,
    )
    finder_result = (
        notify_claim_to_finder(
            finder_email=finder_email,
            category=found.category,
            owner_email=email,
        )
        if finder_email
        else {"sent": False, "reason": "missing_finder_email"}
    )

    notify_message = (
        f"Claim submitted for found item {found.id}. "
        f"Owner email ({email}): {'sent' if owner_result.get('sent') else 'failed'} via {owner_result.get('mode', 'n/a')}. "
        f"Finder email ({finder_email or 'missing'}): "
        f"{'sent' if finder_result.get('sent') else 'not sent'} via {finder_result.get('mode', 'n/a')}."
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
    if not lost.email:
        lost.email = email

    db.add(claim)
    db.commit()
    db.refresh(claim)

    return {
        "id": claim.id,
        "status": claim.status,
        "message": "Claim recorded. Owner and finder have been emailed to arrange pickup.",
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
