from datetime import datetime
from pathlib import Path
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from categories import CATEGORIES
from clip_service import cosine_similarity, encode_pil_image, encode_text, predict_category
from config import settings
from database import get_db
from email_service import (
    mail_delivery_mode,
    notify_exchange_cancelled,
    notify_exchange_processed,
    notify_match_accepted_to_finder,
    notify_match_accepted_to_owner,
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
PICKUP_POINT = "Library Information Desk"


def confirm_page_url(token: str) -> str:
    base = (getattr(settings, "frontend_base_url", None) or "http://localhost:3000").rstrip("/")
    # SPA entry is findit.html (nginx may not serve / as index without that file).
    return f"{base}/findit.html?confirm={token}"


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


def require_user(
    current_user: models.Users | None = Depends(oauth2.get_optional_user),
) -> models.Users:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user


def _apply_confirmation(db, claim, found, lost, role: str) -> str:
    """Record one party's confirmation; mark processed + notify when both agree.

    Shared by the email-token confirm and the authenticated dashboard confirm."""
    if claim.status == "cancelled":
        raise HTTPException(status_code=409, detail="This exchange was cancelled")
    if claim.status == "processed":
        return "This exchange is already processed."

    if role == "owner":
        claim.owner_confirmed = True
    else:
        claim.finder_confirmed = True

    just_processed = False
    if claim.owner_confirmed and claim.finder_confirmed and claim.status != "processed":
        claim.status = "processed"
        if found:
            found.status = "processed"
        if lost:
            lost.status = "processed"
        just_processed = True

        owner_email = normalize_email(claim.claimed_by_email or (lost.email if lost else None))
        finder_email = normalize_email(found.finder_email if found else None)
        category = (found.category if found else None) or (lost.category if lost else None) or "item"
        if owner_email:
            notify_exchange_processed(
                to_email=owner_email,
                category=category,
                other_party_email=finder_email,
            )
        if finder_email and not emails_match(finder_email, owner_email):
            notify_exchange_processed(
                to_email=finder_email,
                category=category,
                other_party_email=owner_email,
            )

    db.commit()
    db.refresh(claim)

    if just_processed:
        return "Both parties confirmed. Item marked processed and removed from open lists."
    if role == "owner":
        return "Owner confirmation recorded. Waiting for the finder to confirm."
    return "Finder confirmation recorded. Waiting for the owner to confirm."


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


LOST_TEXT_DEDUP_THRESHOLD = 0.985


def find_duplicate_lost(
    db: Session,
    *,
    owner_email: str | None,
    owner_user_id: int | None,
    category: str,
    image_embedding: list[float] | None,
    text_embedding: list[float] | None,
) -> models.LostItem | None:
    """Return an existing OPEN lost report from the same owner that is effectively
    the same item (near-identical photo, or near-identical description in the same
    category). This stops repeat "searches" from piling up duplicate open rows."""
    if not owner_email and owner_user_id is None:
        return None

    candidates = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .all()
    )
    for cand in candidates:
        same_owner = (
            (owner_user_id is not None and cand.owner_user_id == owner_user_id)
            or emails_match(cand.email, owner_email)
        )
        if not same_owner:
            continue

        if image_embedding is not None:
            cand_image = embedding_list(cand.image_embedding)
            if cand_image is not None and cosine_similarity(image_embedding, cand_image) >= DEDUP_THRESHOLD:
                return cand

        if text_embedding is not None and cand.category == category:
            cand_text = embedding_list(cand.text_embedding)
            if cand_text is not None and cosine_similarity(text_embedding, cand_text) >= LOST_TEXT_DEDUP_THRESHOLD:
                return cand

    return None


def find_near_duplicate(
    db: Session,
    image_embedding: list[float],
    *,
    finder_email: str | None = None,
    finder_user_id: int | None = None,
) -> models.FoundItem | None:
    """Detect an accidental re-upload by the SAME finder.

    Two different finders can't hold the same physical object, so a near-identical
    photo from a different uploader is NOT a duplicate — only a same-uploader repeat
    of the same available item is."""
    if not finder_email and finder_user_id is None:
        return None

    candidates = (
        db.query(models.FoundItem)
        .filter(models.FoundItem.status == "available")
        .filter(models.FoundItem.image_embedding.isnot(None))
        .all()
    )
    for item in candidates:
        same_finder = (
            (finder_user_id is not None and item.finder_user_id == finder_user_id)
            or emails_match(item.finder_email, finder_email)
        )
        if not same_finder:
            continue
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

    duplicate = find_near_duplicate(
        db,
        image_embedding,
        finder_email=email,
        finder_user_id=current_user.id if current_user else None,
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="You already reported this item as found (near-identical photo).",
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

    # Reverse match against open lost reports (lost filed first, found later).
    # No email yet — finder reviews ranked matches in-app and can accept a pairing.
    open_lost = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .filter(models.LostItem.text_embedding.isnot(None))
        .all()
    )
    ranked_matches: list[dict] = []
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
        ranked_matches.append(
            {
                "id": lost.id,
                "score": hit["score"],
                "category": lost.category,
                "description": lost.description,
                "location": lost.location,
                "date_lost": lost.date_lost,
                "image_url": f"/uploads/{lost.image_path}" if lost.image_path else None,
                "same_category": hit["same_category"],
                "tier": hit["tier"],
                "scores_breakdown": hit["scores_breakdown"],
            }
        )

    ranked_matches.sort(key=lambda m: m["score"], reverse=True)
    for index, match in enumerate(ranked_matches, start=1):
        match["rank"] = index

    top_breakdown = (
        ranked_matches[0]["scores_breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )

    message = "Found item reported successfully"
    if ranked_matches:
        message = (
            f"Found item reported successfully. "
            f"{len(ranked_matches)} possible open lost report(s) matched — review and accept if correct."
        )

    return {
        "id": item.id,
        "message": message,
        "category": item.category,
        "embedding_stored": True,
        "matches": ranked_matches,
        "total_compared": len(open_lost),
        "scores_breakdown": top_breakdown,
        "found_image_url": f"/uploads/{item.image_path}" if item.image_path else None,
        "found_description": item.description,
        "found_location": item.location,
        "found_date": item.date_found,
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

    # Reuse an existing open report from the same owner instead of inserting a
    # duplicate row when someone re-searches with the same photo/description.
    lost_item = find_duplicate_lost(
        db,
        owner_email=owner_email,
        owner_user_id=owner_user_id,
        category=lost_category,
        image_embedding=lost_image_embedding,
        text_embedding=lost_text_embedding,
    )
    if lost_item is not None:
        lost_item.description = description
        lost_item.category = lost_category
        if location:
            lost_item.location = location
        if date_lost:
            lost_item.date_lost = date_lost
        if image_path:
            lost_item.image_path = image_path
        if lost_image_embedding is not None:
            lost_item.image_embedding = lost_image_embedding
        lost_item.text_embedding = lost_text_embedding
        if owner_user_id is not None and lost_item.owner_user_id is None:
            lost_item.owner_user_id = owner_user_id
        db.commit()
        db.refresh(lost_item)
    else:
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
    if lost.status != "open":
        raise HTTPException(status_code=409, detail="This lost report is no longer open for matching")

    initiated_by = (body.initiated_by or "owner").strip().lower()
    if initiated_by not in {"owner", "finder"}:
        raise HTTPException(status_code=400, detail="initiated_by must be 'owner' or 'finder'")

    actor_email = resolve_uploader_email(body.email, current_user)
    finder_email = normalize_email(found.finder_email)
    owner_email = normalize_email(lost.email)

    if initiated_by == "finder":
        # Finder accepts an open lost match (lost was filed first).
        if not emails_match(actor_email, finder_email):
            raise HTTPException(
                status_code=403,
                detail="Only the finder who reported this item can accept a lost match",
            )
        if not owner_email:
            raise HTTPException(
                status_code=400,
                detail="That lost report has no owner email on file",
            )
        if emails_match(owner_email, finder_email):
            raise HTTPException(status_code=400, detail="Cannot pair your own lost and found reports")
    else:
        # Owner claims a found item (classic lost-search flow).
        owner_email = normalize_email(actor_email) or owner_email
        if not owner_email:
            raise HTTPException(status_code=400, detail="Owner email is required")
        if emails_match(owner_email, finder_email):
            raise HTTPException(
                status_code=400,
                detail="You cannot claim an item you reported found yourself",
            )
        if not lost.email:
            lost.email = owner_email

    user_id = current_user.id if current_user else None
    owner_token = secrets.token_urlsafe(24)
    finder_token = secrets.token_urlsafe(24)

    claim = models.Claim(
        found_item_id=found.id,
        lost_item_id=lost.id,
        claimed_by_email=owner_email,
        claimed_by_user_id=user_id if initiated_by == "owner" else None,
        status="in_process",
        owner_confirmed=False,
        finder_confirmed=False,
        owner_confirm_token=owner_token,
        finder_confirm_token=finder_token,
    )
    found.status = "in_process"
    found.claimed_by_lost_id = lost.id
    lost.status = "in_process"

    db.add(claim)
    db.commit()
    db.refresh(claim)

    owner_result = notify_match_accepted_to_owner(
        owner_email=owner_email,
        finder_email=finder_email or "not provided",
        finder_name=found.reported_by,
        category=found.category,
        found_location=found.location,
        lost_location=lost.location,
        pickup_point=PICKUP_POINT,
        confirm_url=confirm_page_url(owner_token),
    )
    finder_result: dict = {"sent": False, "mode": mail_delivery_mode(), "reason": "missing_finder_email"}
    if finder_email:
        finder_result = notify_match_accepted_to_finder(
            finder_email=finder_email,
            finder_name=found.reported_by,
            owner_email=owner_email,
            category=found.category,
            found_location=found.location,
            lost_location=lost.location,
            pickup_point=PICKUP_POINT,
            confirm_url=confirm_page_url(finder_token),
        )

    mail_mode = owner_result.get("mode") or finder_result.get("mode") or mail_delivery_mode()
    notify_message = (
        f"Match accepted by {initiated_by} — status in_process for found {found.id} / lost {lost.id}. "
        f"Owner ({owner_email}): {'sent' if owner_result.get('sent') else 'failed'} via {owner_result.get('mode', 'n/a')}. "
        f"Finder ({finder_email or 'missing'}): "
        f"{'sent' if finder_result.get('sent') else 'not sent'} via {finder_result.get('mode', 'n/a')}."
    )
    claim.notify_message = notify_message
    db.commit()

    return {
        "id": claim.id,
        "status": claim.status,
        "message": (
            "Match accepted. Status is in process. Both parties were emailed each other's contact "
            "and must confirm after a successful exchange."
        ),
        "notify_message": notify_message,
        "owner_email": owner_email,
        "finder_email": finder_email,
        "finder_name": found.reported_by,
        "category": found.category,
        "found_location": found.location,
        "lost_location": lost.location,
        "pickup_point": PICKUP_POINT,
        "mail_mode": mail_mode,
        "owner_mail_sent": bool(owner_result.get("sent")),
        "finder_mail_sent": bool(finder_result.get("sent")),
        "owner_confirmed": False,
        "finder_confirmed": False,
        "owner_confirm_url": confirm_page_url(owner_token) if initiated_by == "owner" else None,
        "finder_confirm_url": confirm_page_url(finder_token) if initiated_by == "finder" else None,
        "exchange_status": "in_process",
    }


@router.post("/claim/confirm", response_model=schemas.ExchangeConfirmResponse)
async def confirm_exchange(
    body: schemas.ExchangeConfirmRequest,
    db: Session = Depends(get_db),
):
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Confirmation token is required")

    claim = (
        db.query(models.Claim)
        .filter(
            (models.Claim.owner_confirm_token == token)
            | (models.Claim.finder_confirm_token == token)
        )
        .first()
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Invalid or expired confirmation link")

    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()
    if not found or not lost:
        raise HTTPException(status_code=404, detail="Linked items not found")

    role = "owner" if claim.owner_confirm_token == token else "finder"
    message = _apply_confirmation(db, claim, found, lost, role)

    return {
        "claim_id": claim.id,
        "role": role,
        "status": claim.status,
        "owner_confirmed": bool(claim.owner_confirmed),
        "finder_confirmed": bool(claim.finder_confirmed),
        "message": message,
        "category": found.category,
        "processed": claim.status == "processed",
    }


@router.get("/claim/confirm", response_model=schemas.ExchangeConfirmResponse)
async def confirm_exchange_get(token: str, db: Session = Depends(get_db)):
    return await confirm_exchange(schemas.ExchangeConfirmRequest(token=token), db)


@router.post("/claim/confirm-auth", response_model=schemas.ExchangeConfirmResponse)
async def confirm_exchange_authenticated(
    body: schemas.ClaimConfirmAuthRequest,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    """Confirm an exchange from the authenticated dashboard (no email token needed).

    The caller's identity determines whether they confirm as owner or finder."""
    claim = db.query(models.Claim).filter(models.Claim.id == body.claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()
    if not found or not lost:
        raise HTTPException(status_code=404, detail="Linked items not found")

    email = normalize_email(current_user.email)
    is_owner = (
        emails_match(claim.claimed_by_email, email)
        or emails_match(lost.email, email)
        or lost.owner_user_id == current_user.id
        or claim.claimed_by_user_id == current_user.id
    )
    is_finder = emails_match(found.finder_email, email) or found.finder_user_id == current_user.id
    if is_owner:
        role = "owner"
    elif is_finder:
        role = "finder"
    else:
        raise HTTPException(status_code=403, detail="Only a participant can confirm this exchange")

    message = _apply_confirmation(db, claim, found, lost, role)
    return {
        "claim_id": claim.id,
        "role": role,
        "status": claim.status,
        "owner_confirmed": bool(claim.owner_confirmed),
        "finder_confirmed": bool(claim.finder_confirmed),
        "message": message,
        "category": found.category,
        "processed": claim.status == "processed",
    }


@router.post("/claim/cancel", response_model=schemas.ClaimCancelResponse)
async def cancel_claim(
    body: schemas.ClaimCancelRequest,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    """Cancel an in-process exchange and reopen both items for matching.

    Only a participant (owner or finder) may cancel."""
    claim = None
    if body.claim_id:
        claim = db.query(models.Claim).filter(models.Claim.id == body.claim_id).first()
    elif body.found_item_id and body.lost_item_id:
        claim = (
            db.query(models.Claim)
            .filter(
                models.Claim.found_item_id == body.found_item_id,
                models.Claim.lost_item_id == body.lost_item_id,
            )
            .order_by(models.Claim.created_at.desc())
            .first()
        )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != "in_process":
        raise HTTPException(status_code=409, detail="Only in-process exchanges can be cancelled")

    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()

    actor_email = normalize_email(current_user.email)
    owner_email = normalize_email(claim.claimed_by_email or (lost.email if lost else None))
    finder_email = normalize_email(found.finder_email if found else None)

    is_participant = (
        emails_match(actor_email, owner_email)
        or emails_match(actor_email, finder_email)
        or (lost is not None and lost.owner_user_id == current_user.id)
        or (found is not None and found.finder_user_id == current_user.id)
        or claim.claimed_by_user_id == current_user.id
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Only a participant can cancel this exchange")

    claim.status = "cancelled"
    if found and found.status == "in_process":
        found.status = "available"
        found.claimed_by_lost_id = None
    if lost and lost.status == "in_process":
        lost.status = "open"
    db.commit()

    cancelled_by = format_reported_by(actor_email, current_user.full_name) or actor_email
    category = (found.category if found else None) or (lost.category if lost else None) or "item"
    if owner_email:
        notify_exchange_cancelled(
            to_email=owner_email,
            category=category,
            cancelled_by=cancelled_by,
            other_party_email=finder_email,
        )
    if finder_email and not emails_match(finder_email, owner_email):
        notify_exchange_cancelled(
            to_email=finder_email,
            category=category,
            cancelled_by=cancelled_by,
            other_party_email=owner_email,
        )

    return {
        "claim_id": claim.id,
        "status": claim.status,
        "message": "Exchange cancelled. Both items are open again for matching.",
        "found_status": found.status if found else None,
        "lost_status": lost.status if lost else None,
    }


@router.get("/me/dashboard", response_model=schemas.DashboardResponse)
async def my_dashboard(
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    email = normalize_email(current_user.email)

    lost_items = (
        db.query(models.LostItem)
        .filter(
            (models.LostItem.owner_user_id == current_user.id)
            | (models.LostItem.email == email)
        )
        .order_by(models.LostItem.created_at.desc())
        .all()
    )
    found_items = (
        db.query(models.FoundItem)
        .filter(
            (models.FoundItem.finder_user_id == current_user.id)
            | (models.FoundItem.finder_email == email)
        )
        .order_by(models.FoundItem.created_at.desc())
        .all()
    )

    lost_ids = {item.id for item in lost_items}
    found_ids = {item.id for item in found_items}

    claims = (
        db.query(models.Claim)
        .filter(
            models.Claim.found_item_id.in_(found_ids or {""})
            | models.Claim.lost_item_id.in_(lost_ids or {""})
            | (models.Claim.claimed_by_email == email)
            | (models.Claim.claimed_by_user_id == current_user.id)
        )
        .order_by(models.Claim.created_at.desc())
        .all()
    )

    # Preload any linked items not already in the user's own lists.
    found_map = {item.id: item for item in found_items}
    lost_map = {item.id: item for item in lost_items}
    missing_found = {c.found_item_id for c in claims} - set(found_map)
    missing_lost = {c.lost_item_id for c in claims} - set(lost_map)
    if missing_found:
        for item in db.query(models.FoundItem).filter(models.FoundItem.id.in_(missing_found)).all():
            found_map[item.id] = item
    if missing_lost:
        for item in db.query(models.LostItem).filter(models.LostItem.id.in_(missing_lost)).all():
            lost_map[item.id] = item

    dashboard_claims = []
    for claim in claims:
        found = found_map.get(claim.found_item_id)
        lost = lost_map.get(claim.lost_item_id)

        is_owner = (
            claim.lost_item_id in lost_ids
            or emails_match(claim.claimed_by_email, email)
            or claim.claimed_by_user_id == current_user.id
        )
        is_finder = claim.found_item_id in found_ids or (
            found is not None and emails_match(found.finder_email, email)
        )
        role = "owner" if is_owner else "finder" if is_finder else "participant"

        if role == "finder":
            counterpart = normalize_email(claim.claimed_by_email or (lost.email if lost else None))
        else:
            counterpart = normalize_email(found.finder_email if found else None)

        dashboard_claims.append(
            {
                "id": claim.id,
                "found_item_id": claim.found_item_id,
                "lost_item_id": claim.lost_item_id,
                "status": claim.status,
                "role": role,
                "owner_confirmed": bool(claim.owner_confirmed),
                "finder_confirmed": bool(claim.finder_confirmed),
                "category": (found.category if found else None) or (lost.category if lost else None),
                "counterpart_email": counterpart,
                "found_location": found.location if found else None,
                "lost_location": lost.location if lost else None,
                "can_cancel": claim.status == "in_process",
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
        )

    def lost_admin(item: models.LostItem) -> dict:
        return {
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

    def found_admin(item: models.FoundItem) -> dict:
        return {
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

    return {
        "email": email,
        "lost_items": [lost_admin(item) for item in lost_items],
        "found_items": [found_admin(item) for item in found_items],
        "claims": dashboard_claims,
    }


@router.post("/claim/contact", response_model=schemas.ContactEmailResponse)
async def resend_claim_contact_email(
    body: schemas.ContactEmailRequest,
    db: Session = Depends(get_db),
    current_user: models.Users | None = Depends(oauth2.get_optional_user),
):
    """Resend match-accepted emails while an exchange is still in process."""
    found = db.query(models.FoundItem).filter(models.FoundItem.id == body.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == body.lost_item_id).first()
    if not found or not lost:
        raise HTTPException(status_code=404, detail="Found or lost item not found")
    if found.status != "in_process" or lost.status != "in_process":
        raise HTTPException(status_code=409, detail="Exchange must be in process to resend contact emails")

    claim = (
        db.query(models.Claim)
        .filter(models.Claim.found_item_id == found.id, models.Claim.lost_item_id == lost.id)
        .order_by(models.Claim.created_at.desc())
        .first()
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for this pair")

    email = resolve_uploader_email(body.email or lost.email, current_user)
    finder_email = normalize_email(found.finder_email)
    if not finder_email:
        raise HTTPException(status_code=400, detail="Finder has no email on file")

    if not claim.owner_confirm_token:
        claim.owner_confirm_token = secrets.token_urlsafe(24)
    if not claim.finder_confirm_token:
        claim.finder_confirm_token = secrets.token_urlsafe(24)
    db.commit()

    owner_result = notify_match_accepted_to_owner(
        owner_email=email,
        finder_email=finder_email,
        finder_name=found.reported_by,
        category=found.category,
        found_location=found.location,
        lost_location=lost.location,
        pickup_point=PICKUP_POINT,
        confirm_url=confirm_page_url(claim.owner_confirm_token),
    )
    finder_result = notify_match_accepted_to_finder(
        finder_email=finder_email,
        finder_name=found.reported_by,
        owner_email=email,
        category=found.category,
        found_location=found.location,
        lost_location=lost.location,
        pickup_point=PICKUP_POINT,
        confirm_url=confirm_page_url(claim.finder_confirm_token),
    )
    mail_mode = owner_result.get("mode") or finder_result.get("mode") or mail_delivery_mode()

    return {
        "message": (
            "Match-accepted emails resent."
            if mail_mode == "smtp"
            else "Emails written to server outbox (configure SMTP for live delivery)."
        ),
        "mail_mode": mail_mode,
        "owner_mail_sent": bool(owner_result.get("sent")),
        "finder_mail_sent": bool(finder_result.get("sent")),
        "owner_email": email,
        "finder_email": finder_email,
        "finder_name": found.reported_by,
        "category": found.category,
        "found_location": found.location,
        "lost_location": lost.location,
        "pickup_point": PICKUP_POINT,
        "notify_message": (
            f"Owner ({email}): {'sent' if owner_result.get('sent') else 'failed'} via {owner_result.get('mode')}; "
            f"Finder ({finder_email}): {'sent' if finder_result.get('sent') else 'failed'} via {finder_result.get('mode')}"
        ),
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
                "owner_confirmed": bool(claim.owner_confirmed),
                "finder_confirmed": bool(claim.finder_confirmed),
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
                "owner_confirmed": bool(claim.owner_confirmed),
                "finder_confirmed": bool(claim.finder_confirmed),
                "notify_message": claim.notify_message,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
            for claim in claims
        ],
    }
