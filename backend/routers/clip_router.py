from datetime import datetime
from pathlib import Path
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy import or_
from sqlalchemy.orm import Session

from categories import CATEGORIES, SERIAL_LIKELY_CATEGORIES
from clip_service import as_vec, cosine_similarity, encode_pil_image, encode_text, predict_category
from validation import validate_item_description
from config import settings
from database import get_db
from email_service import (
    mail_delivery_mode,
    notify_exchange_cancelled,
    notify_match_accepted_to_finder,
    notify_match_accepted_to_owner,
    notify_match_to_finder,
    notify_match_to_owner,
)
from image_utils import read_and_sanitize_image
from locations import validate_found_location, validate_lost_locations
from matching import compare_serials, compute_match, locations_overlap
import models
import oauth2
import schemas

HIGH_VALUE_CATEGORIES = {"Gadgets", "Electronics", "Gadget Accessories", "Wallet / Purse"}


def _parse_bool_form(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_serial(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(str(value).strip().split())
    return cleaned or None


def _high_value_flag(explicit: str | None, category: str) -> bool:
    # Honor the checkbox when the client sends it; otherwise hint from category.
    if explicit is not None and str(explicit).strip() != "":
        return _parse_bool_form(explicit)
    return category in SERIAL_LIKELY_CATEGORIES or category in HIGH_VALUE_CATEGORIES


def _serial_status_payload(lost: models.LostItem | None, found: models.FoundItem | None) -> dict:
    lost_serial = lost.serial_number if lost else None
    found_serial = found.serial_number if found else None
    status = compare_serials(lost_serial, found_serial)
    return {
        "serial_status": status,
        "lost_has_serial": bool(_normalize_serial(lost_serial)),
        "found_has_serial": bool(_normalize_serial(found_serial)),
        "lost_serial": lost_serial,
        "found_serial": found_serial,
        "lost_marks": lost.distinctive_marks if lost else None,
        "found_marks": found.distinctive_marks if found else None,
        "serial_likely_category": bool(
            (lost and lost.category in SERIAL_LIKELY_CATEGORIES)
            or (found and found.category in SERIAL_LIKELY_CATEGORIES)
        ),
    }


router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DEDUP_THRESHOLD = 0.98


def confirm_page_url(token: str) -> str:
    base = (getattr(settings, "frontend_base_url", None) or "http://localhost:3000").rstrip("/")
    # emails open amalost.html?confirm=
    return f"{base}/amalost.html?confirm={token}"


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def uploader_email(
    form_email: str | None,
    current_user: models.Users | None,
    *,
    required: bool = True,
) -> str | None:
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


def user_owns_lost(user: models.Users, item: models.LostItem) -> bool:
    if item.owner_user_id is not None and item.owner_user_id == user.id:
        return True
    return emails_match(item.email, user.email)


def user_owns_found(user: models.Users, item: models.FoundItem) -> bool:
    if item.finder_user_id is not None and item.finder_user_id == user.id:
        return True
    return emails_match(item.finder_email, user.email)


def _delete_lost_item(db: Session, item: models.LostItem) -> None:
    claims = db.query(models.Claim).filter(models.Claim.lost_item_id == item.id).all()
    for claim in claims:
        if claim.status == "in_process" or claim.status == "at_desk":
            _reopen_items_for_claim(db, claim)
        db.delete(claim)
    image_path = item.image_path
    db.delete(item)
    db.commit()
    _remove_upload_file(image_path)


def _delete_found_item(db: Session, item: models.FoundItem) -> None:
    claims = db.query(models.Claim).filter(models.Claim.found_item_id == item.id).all()
    for claim in claims:
        if claim.status == "in_process" or claim.status == "at_desk":
            _reopen_items_for_claim(db, claim)
        db.delete(claim)
    image_path = item.image_path
    db.delete(item)
    db.commit()
    _remove_upload_file(image_path)


def _apply_confirmation(db, claim, found, lost, role: str) -> str:
    if claim.status == "cancelled":
        raise HTTPException(status_code=409, detail="This exchange was cancelled")
    if claim.status == "processed":
        return "This exchange is already processed."

    if role == "owner":
        claim.owner_confirmed = True
    else:
        claim.finder_confirmed = True

    db.commit()
    db.refresh(claim)

    # Dual confirm acknowledges the parties are ready; staff desk custody still
    # must receive and release the item before status becomes processed.
    if claim.desk_released and claim.status == "processed":
        return "This exchange is already processed."
    if claim.owner_confirmed and claim.finder_confirmed:
        if claim.desk_received:
            return (
                "Both parties confirmed. Item is at the campus desk — "
                "waiting for staff to release it to the owner."
            )
        return (
            "Both parties confirmed. Please complete the exchange through the "
            "campus lost-and-found desk; staff must receive and release the item."
        )
    if role == "owner":
        return "Owner confirmation recorded. Waiting for the finder to confirm."
    return "Finder confirmation recorded. Waiting for the owner to confirm."


def _mark_desk_received(db, claim, found, lost) -> str:
    if claim.status == "cancelled":
        raise HTTPException(status_code=409, detail="This exchange was cancelled")
    if claim.status == "processed":
        return "This exchange is already processed."
    claim.desk_received = True
    claim.status = "at_desk"
    if found and found.status == "in_process":
        found.status = "at_desk"
    if lost and lost.status == "in_process":
        lost.status = "at_desk"
    db.commit()
    return "Item marked received at the campus lost-and-found desk."


def _mark_desk_released(db, claim, found, lost) -> str:
    if claim.status == "cancelled":
        raise HTTPException(status_code=409, detail="This exchange was cancelled")
    if not claim.desk_received:
        raise HTTPException(
            status_code=409,
            detail="Receive the item at the desk before releasing it to the owner",
        )
    claim.desk_released = True
    claim.status = "processed"
    if found:
        found.status = "processed"
    if lost:
        lost.status = "processed"
    db.commit()
    return "Item released to the owner. Exchange marked processed."


def short_name(email: str | None, full_name: str | None = None) -> str | None:
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


TEXT_DEDUP = 0.985


def find_dup_lost(
    db: Session,
    *,
    owner_email: str | None,
    owner_user_id: int | None,
    category: str,
    image_embedding: list[float] | None,
    text_embedding: list[float] | None,
) -> models.LostItem | None:
    if not owner_email and owner_user_id is None:
        return None

    owner_filters = []
    if owner_user_id is not None:
        owner_filters.append(models.LostItem.owner_user_id == owner_user_id)
    owner_email_norm = normalize_email(owner_email)
    if owner_email_norm:
        owner_filters.append(models.LostItem.email == owner_email_norm)
    if not owner_filters:
        return None
    candidates = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .filter(or_(*owner_filters))
        .all()
    )
    for cand in candidates:
        if image_embedding is not None:
            cand_image = as_vec(cand.image_embedding)
            if cand_image is not None and cosine_similarity(image_embedding, cand_image) >= DEDUP_THRESHOLD:
                return cand

        if text_embedding is not None and cand.category == category:
            cand_text = as_vec(cand.text_embedding)
            if cand_text is not None and cosine_similarity(text_embedding, cand_text) >= TEXT_DEDUP:
                return cand

    return None


def find_near_dup(
    db: Session,
    image_embedding: list[float],
    *,
    finder_email: str | None = None,
    finder_user_id: int | None = None,
) -> models.FoundItem | None:
    if not finder_email and finder_user_id is None:
        return None

    finder_filters = []
    if finder_user_id is not None:
        finder_filters.append(models.FoundItem.finder_user_id == finder_user_id)
    finder_email_norm = normalize_email(finder_email)
    if finder_email_norm:
        finder_filters.append(models.FoundItem.finder_email == finder_email_norm)
    if not finder_filters:
        return None
    candidates = (
        db.query(models.FoundItem)
        .filter(models.FoundItem.status == "available")
        .filter(models.FoundItem.image_embedding.isnot(None))
        .filter(or_(*finder_filters))
        .all()
    )
    for item in candidates:
        existing = as_vec(item.image_embedding)
        if existing is None:
            continue
        if cosine_similarity(image_embedding, existing) >= DEDUP_THRESHOLD:
            return item
    return None


# drop the long same-category tail after the leading cluster
MATCH_MIN_KEEP = 3
MATCH_LEAD_MARGIN = 0.08
MATCH_GAP = 0.035
MATCH_MAX_KEEP = 12


def trim_ranked_matches(matches: list[dict]) -> list[dict]:
    if len(matches) <= MATCH_MIN_KEEP:
        return matches
    top = matches[0]["score"]
    kept = list(matches[:MATCH_MIN_KEEP])
    for i in range(MATCH_MIN_KEEP, min(len(matches), MATCH_MAX_KEEP)):
        cur = matches[i]["score"]
        prev = matches[i - 1]["score"]
        if (top - cur) > MATCH_LEAD_MARGIN:
            break
        if (prev - cur) > MATCH_GAP:
            break
        kept.append(matches[i])
    return kept


def lost_has_prior_open_matches(
    db: Session,
    lost: models.LostItem,
    *,
    exclude_found_id: str | None = None,
) -> bool:
    """True if this open lost report already has another available found match."""
    lost_text = as_vec(lost.text_embedding)
    if lost_text is None:
        return False
    query = db.query(models.FoundItem).filter(models.FoundItem.status == "available")
    if exclude_found_id:
        query = query.filter(models.FoundItem.id != exclude_found_id)
    for found in query.all():
        if emails_match(found.finder_email, lost.email):
            continue
        hit = score_lost_against_found(
            lost_text_embedding=lost_text,
            lost_image_embedding=as_vec(lost.image_embedding),
            lost_category=lost.category,
            lost_location=lost.location,
            lost_date=lost.date_lost,
            found=found,
            lost_serial=lost.serial_number,
        )
        if hit is not None:
            return True
    return False


def found_has_prior_open_matches(
    db: Session,
    found: models.FoundItem,
    *,
    exclude_lost_id: str | None = None,
) -> bool:
    """True if this available found item already has another open lost match."""
    query = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .filter(models.LostItem.text_embedding.isnot(None))
    )
    if exclude_lost_id:
        query = query.filter(models.LostItem.id != exclude_lost_id)
    for lost in query.all():
        if emails_match(lost.email, found.finder_email):
            continue
        lost_text = as_vec(lost.text_embedding)
        if lost_text is None:
            continue
        hit = score_lost_against_found(
            lost_text_embedding=lost_text,
            lost_image_embedding=as_vec(lost.image_embedding),
            lost_category=lost.category,
            lost_location=lost.location,
            lost_date=lost.date_lost,
            found=found,
            lost_serial=lost.serial_number,
        )
        if hit is not None:
            return True
    return False


def score_lost_against_found(
    *,
    lost_text_embedding: list[float],
    lost_image_embedding: list[float] | None,
    lost_category: str,
    lost_location: str | None,
    lost_date: str | None,
    found: models.FoundItem,
    apply_location_boost: bool = True,
    lost_serial: str | None = None,
) -> dict | None:
    found_image = as_vec(found.image_embedding)
    found_text = as_vec(found.text_embedding)
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
    text_to_text = (
        cosine_similarity(lost_text_embedding, found_text)
        if (found_text is not None and lost_text_embedding is not None)
        else None
    )

    final_score, tier, same_category, scores_breakdown = compute_match(
        text_to_image=text_to_image,
        image_to_image=image_to_image,
        found_text_to_lost_image=found_text_to_lost_image,
        text_to_text=text_to_text,
        lost_category=lost_category,
        found_category=found.category,
        lost_location=lost_location,
        found_location=found.location,
        lost_date=lost_date,
        found_date=found.date_found,
        apply_location_boost=apply_location_boost,
    )
    if tier is None:
        return None

    same_location = locations_overlap(lost_location, found.location)

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
        "same_location": same_location,
        "tier": tier,
        "scores_breakdown": scores_breakdown,
        "finder_email": found.finder_email,
        "is_high_value": bool(found.is_high_value) or found.category in HIGH_VALUE_CATEGORIES,
        "serial_on_file": bool(_normalize_serial(found.serial_number)),
        "serial_status": compare_serials(lost_serial, found.serial_number),
    }


def rank_found_matches_for_lost(
    db: Session,
    lost: models.LostItem,
    *,
    apply_location_boost: bool = True,
) -> tuple[list[dict], int]:
    lost_text = as_vec(lost.text_embedding)
    if lost_text is None:
        return [], 0
    lost_image = as_vec(lost.image_embedding)
    found_items = (
        db.query(models.FoundItem)
        .filter(models.FoundItem.status == "available")
        .all()
    )

    ranked: list[dict] = []
    for found in found_items:
        if emails_match(found.finder_email, lost.email):
            continue
        hit = score_lost_against_found(
            lost_text_embedding=lost_text,
            lost_image_embedding=lost_image,
            lost_category=lost.category,
            lost_location=lost.location,
            lost_date=lost.date_lost,
            found=found,
            apply_location_boost=apply_location_boost,
            lost_serial=lost.serial_number,
        )
        if hit is None:
            continue
        ranked.append({k: v for k, v in hit.items() if k != "finder_email"})

    ranked.sort(key=lambda m: m["score"], reverse=True)
    for index, match in enumerate(ranked, start=1):
        match["rank"] = index
    return trim_ranked_matches(ranked), len(found_items)


def rank_lost_matches_for_found(db: Session, found: models.FoundItem) -> tuple[list[dict], int]:
    open_lost = (
        db.query(models.LostItem)
        .filter(models.LostItem.status == "open")
        .filter(models.LostItem.text_embedding.isnot(None))
        .all()
    )
    ranked: list[dict] = []
    for lost in open_lost:
        if emails_match(lost.email, found.finder_email):
            continue
        lost_text = as_vec(lost.text_embedding)
        if lost_text is None:
            continue
        hit = score_lost_against_found(
            lost_text_embedding=lost_text,
            lost_image_embedding=as_vec(lost.image_embedding),
            lost_category=lost.category,
            lost_location=lost.location,
            lost_date=lost.date_lost,
            found=found,
            lost_serial=lost.serial_number,
        )
        if hit is None:
            continue
        ranked.append(
            {
                "id": lost.id,
                "score": hit["score"],
                "category": lost.category,
                "description": lost.description,
                "location": lost.location,
                "date_lost": lost.date_lost,
                "image_url": f"/uploads/{lost.image_path}" if lost.image_path else None,
                "same_category": hit["same_category"],
                "same_location": hit.get("same_location", False),
                "tier": hit["tier"],
                "scores_breakdown": hit["scores_breakdown"],
                "is_high_value": bool(lost.is_high_value) or lost.category in HIGH_VALUE_CATEGORIES,
                "serial_on_file": bool(_normalize_serial(lost.serial_number)),
                "serial_status": hit.get("serial_status", "unknown"),
            }
        )

    ranked.sort(key=lambda m: m["score"], reverse=True)
    for index, match in enumerate(ranked, start=1):
        match["rank"] = index
    return trim_ranked_matches(ranked), len(open_lost)


@router.post("/predict-category", response_model=schemas.CategoryPredictionResponse)
async def predict_item_category(
    image: UploadFile = File(...),
    _user: models.Users = Depends(require_user),
):
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
    is_high_value: str | None = Form(None),
    serial_number: str | None = Form(None),
    distinctive_marks: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")

    try:
        description = validate_item_description(description, required=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        location = validate_found_location(location)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if date_found:
        date_found = date_found.strip()

    # Authenticated uploads are bound to the signed-in account
    email = normalize_email(current_user.email) or uploader_email(finder_email, current_user)

    try:
        pil_image, jpeg_bytes = await read_and_sanitize_image(image)
        image_embedding = encode_pil_image(pil_image)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image")

    duplicate = find_near_dup(
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

    reported_by = short_name(
        email,
        current_user.full_name,
    )
    finder_user_id = current_user.id
    high_value = _high_value_flag(is_high_value, category)
    serial = _normalize_serial(serial_number)
    marks = _normalize_serial(distinctive_marks)

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
        is_high_value=high_value,
        serial_number=serial,
        distinctive_marks=marks,
        status="available",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    ranked_matches, total_compared = rank_lost_matches_for_found(db, item)

    # First-match alert only: email lost owners who previously had zero open matches.
    lost_rows = {}
    if ranked_matches:
        lost_ids = [match["id"] for match in ranked_matches]
        lost_rows = {
            row.id: row
            for row in db.query(models.LostItem).filter(models.LostItem.id.in_(lost_ids)).all()
        }
    for match in ranked_matches:
        lost = lost_rows.get(match["id"])
        if not lost or lost.status != "open":
            continue
        owner = normalize_email(lost.email)
        if not owner or emails_match(owner, email):
            continue
        if lost_has_prior_open_matches(db, lost, exclude_found_id=item.id):
            continue
        notify_match_to_owner(
            owner_email=owner,
            category=lost.category or category,
            match_count=1,
            top_score=match.get("score"),
        )

    top_breakdown = (
        ranked_matches[0]["scores_breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )

    message = "Found item reported. No matching lost reports yet."
    if ranked_matches:
        message = (
            f"Found item reported. "
            f"{len(ranked_matches)} possible lost report(s) matched — review and accept if correct."
        )

    return {
        "id": item.id,
        "message": message,
        "category": item.category,
        "embedding_stored": True,
        "matches": ranked_matches,
        "total_compared": total_compared,
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
    search_all_locations: str | None = Form(None),
    is_high_value: str | None = Form(None),
    serial_number: str | None = Form(None),
    distinctive_marks: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    search_all = category == "All"
    preferred_category = original_category if search_all and original_category else category
    if preferred_category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(CATEGORIES)}",
        )

    try:
        description = validate_item_description(description, required=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        location = validate_lost_locations(location)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if date_lost:
        date_lost = date_lost.strip()

    # location boost off when "search all locations" is set
    apply_location_boost = str(search_all_locations or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }

    owner_email = normalize_email(current_user.email) or uploader_email(email, current_user)

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
    owner_user_id = current_user.id

    # reuse open row if same owner re-searches the same item
    lost_item = find_dup_lost(
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
        lost_item.is_high_value = _high_value_flag(is_high_value, lost_category)
        lost_item.serial_number = _normalize_serial(serial_number)
        lost_item.distinctive_marks = _normalize_serial(distinctive_marks)
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
            is_high_value=_high_value_flag(is_high_value, lost_category),
            serial_number=_normalize_serial(serial_number),
            distinctive_marks=_normalize_serial(distinctive_marks),
            status="open",
        )
        db.add(lost_item)
        db.commit()
        db.refresh(lost_item)

    category_searched = "All categories" if search_all else category
    ranked_matches, total_compared = rank_found_matches_for_lost(
        db,
        lost_item,
        apply_location_boost=apply_location_boost,
    )

    # First-match alert only: email finders who previously had zero open lost matches.
    found_rows = {}
    if ranked_matches:
        found_ids = [match["id"] for match in ranked_matches]
        found_rows = {
            row.id: row
            for row in db.query(models.FoundItem).filter(models.FoundItem.id.in_(found_ids)).all()
        }
    for match in ranked_matches:
        found = found_rows.get(match["id"])
        if not found or found.status != "available":
            continue
        finder = normalize_email(found.finder_email)
        if not finder or emails_match(finder, owner_email):
            continue
        if found_has_prior_open_matches(db, found, exclude_lost_id=lost_item.id):
            continue
        notify_match_to_finder(
            finder_email=finder,
            category=found.category or lost_category,
            location=found.location,
        )

    top_breakdown = (
        ranked_matches[0]["scores_breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )

    location_scope = (
        "All campus locations"
        if not apply_location_boost
        else f"Preferring: {location}"
    )

    return {
        "id": lost_item.id,
        "matches": ranked_matches,
        "total_compared": total_compared,
        "category_searched": category_searched,
        "location_scope": location_scope,
        "search_all_locations": not apply_location_boost,
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
    current_user: models.Users = Depends(require_user),
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

    actor_email = normalize_email(current_user.email) or uploader_email(body.email, current_user)
    finder_email = normalize_email(found.finder_email)
    owner_email = normalize_email(lost.email)

    if initiated_by == "finder":
        # finder accepting a lost match
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
        # owner claiming a found item
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

    user_id = current_user.id
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
            confirm_url=confirm_page_url(finder_token),
        )

    mail_mode = owner_result.get("mode") or finder_result.get("mode") or mail_delivery_mode()
    notify_message = (
        f"Match accepted by {initiated_by}. Bring the item to the campus lost-and-found desk. "
        f"Owner email {'sent' if owner_result.get('sent') else 'not sent'}; "
        f"finder email {'sent' if finder_result.get('sent') else 'not sent'}."
    )
    claim.notify_message = notify_message
    db.commit()

    return {
        "id": claim.id,
        "status": claim.status,
        "message": (
            "Match accepted. Status is in process. Contact details were shared; "
            "complete the handover at the campus lost-and-found desk. Staff must "
            "receive and release the item before it is marked processed."
        ),
        "notify_message": notify_message,
        "owner_email": owner_email,
        "finder_email": finder_email,
        "finder_name": found.reported_by,
        "category": found.category,
        "found_location": found.location,
        "lost_location": lost.location,
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
    if claim.status not in ("in_process", "at_desk"):
        raise HTTPException(status_code=409, detail="Only active exchanges can be cancelled")

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

    cancelled_by = short_name(actor_email, current_user.full_name) or actor_email
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

    # pull linked items that aren't already in the user's lists
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

        owner_email = normalize_email(
            claim.claimed_by_email or (lost.email if lost else None)
        )
        finder_email = normalize_email(found.finder_email if found else None)
        if role == "finder":
            counterpart = owner_email
        else:
            counterpart = finder_email

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
                "owner_email": owner_email,
                "finder_email": finder_email,
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
    current_user: models.Users = Depends(require_user),
):
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

    actor = normalize_email(current_user.email)
    is_participant = (
        emails_match(actor, found.finder_email)
        or emails_match(actor, lost.email)
        or emails_match(actor, claim.claimed_by_email)
        or found.finder_user_id == current_user.id
        or lost.owner_user_id == current_user.id
        or claim.claimed_by_user_id == current_user.id
    )
    if not is_participant and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only exchange participants can resend contact emails")

    email = normalize_email(lost.email) or actor
    finder_email = normalize_email(found.finder_email)
    if not finder_email:
        raise HTTPException(status_code=400, detail="Finder has no email on file")
    if not email:
        raise HTTPException(status_code=400, detail="Owner has no email on file")

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
        confirm_url=confirm_page_url(claim.owner_confirm_token),
    )
    finder_result = notify_match_accepted_to_finder(
        finder_email=finder_email,
        finder_name=found.reported_by,
        owner_email=email,
        category=found.category,
        found_location=found.location,
        lost_location=lost.location,
        confirm_url=confirm_page_url(claim.finder_confirm_token),
    )
    mail_mode = owner_result.get("mode") or finder_result.get("mode") or mail_delivery_mode()

    return {
        "message": (
            "Match-accepted emails resent."
            if mail_mode == "smtp"
            else "Could not send email. Use the in-app contact details to coordinate the desk handover."
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
        "notify_message": (
            f"Owner email {'sent' if owner_result.get('sent') else 'not sent'}; "
            f"finder email {'sent' if finder_result.get('sent') else 'not sent'}."
        ),
    }


def _remove_upload_file(image_path: str | None) -> None:
    if not image_path:
        return
    path = UPLOAD_DIR / image_path
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _reopen_items_for_claim(db: Session, claim: models.Claim) -> tuple[models.FoundItem | None, models.LostItem | None]:
    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()
    if found and found.status in ("in_process", "at_desk"):
        found.status = "available"
        found.claimed_by_lost_id = None
    if lost and lost.status in ("in_process", "at_desk"):
        lost.status = "open"
    claim.desk_received = False
    claim.desk_released = False
    return found, lost


def _find_claim_for_admin_cancel(
    db: Session,
    *,
    claim_id: str | None = None,
    found_item_id: str | None = None,
    lost_item_id: str | None = None,
) -> models.Claim | None:
    if claim_id:
        return db.query(models.Claim).filter(models.Claim.id == claim_id).first()
    if found_item_id and lost_item_id:
        return (
            db.query(models.Claim)
            .filter(
                models.Claim.found_item_id == found_item_id,
                models.Claim.lost_item_id == lost_item_id,
            )
            .order_by(models.Claim.created_at.desc())
            .first()
        )
    if found_item_id:
        return (
            db.query(models.Claim)
            .filter(
                models.Claim.found_item_id == found_item_id,
                models.Claim.status == "in_process",
            )
            .order_by(models.Claim.created_at.desc())
            .first()
        )
    if lost_item_id:
        return (
            db.query(models.Claim)
            .filter(
                models.Claim.lost_item_id == lost_item_id,
                models.Claim.status == "in_process",
            )
            .order_by(models.Claim.created_at.desc())
            .first()
        )
    return None


@router.get("/admin/queue", response_model=schemas.AdminQueueResponse)
async def admin_queue(
    db: Session = Depends(get_db),
    _admin: models.Users = Depends(oauth2.get_admin_user),
):
    found_items = db.query(models.FoundItem).order_by(models.FoundItem.created_at.desc()).limit(500).all()
    lost_items = db.query(models.LostItem).order_by(models.LostItem.created_at.desc()).limit(500).all()
    claims = db.query(models.Claim).order_by(models.Claim.created_at.desc()).limit(500).all()

    found_by_id = {item.id: item for item in found_items}
    lost_by_id = {item.id: item for item in lost_items}

    # Claims may reference items outside the capped lists — load missing pairs for contact emails.
    missing_found = {c.found_item_id for c in claims} - set(found_by_id)
    missing_lost = {c.lost_item_id for c in claims} - set(lost_by_id)
    if missing_found:
        for item in db.query(models.FoundItem).filter(models.FoundItem.id.in_(missing_found)).all():
            found_by_id[item.id] = item
    if missing_lost:
        for item in db.query(models.LostItem).filter(models.LostItem.id.in_(missing_lost)).all():
            lost_by_id[item.id] = item

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
                "is_high_value": bool(item.is_high_value),
                "serial_number": item.serial_number,
                "distinctive_marks": item.distinctive_marks,
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
                "is_high_value": bool(item.is_high_value),
                "serial_number": item.serial_number,
                "distinctive_marks": item.distinctive_marks,
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
                "owner_email": normalize_email(
                    claim.claimed_by_email
                    or (lost_by_id[claim.lost_item_id].email if claim.lost_item_id in lost_by_id else None)
                ),
                "finder_email": normalize_email(
                    found_by_id[claim.found_item_id].finder_email
                    if claim.found_item_id in found_by_id
                    else None
                ),
                "category": (
                    (found_by_id[claim.found_item_id].category if claim.found_item_id in found_by_id else None)
                    or (lost_by_id[claim.lost_item_id].category if claim.lost_item_id in lost_by_id else None)
                ),
                "status": claim.status,
                "owner_confirmed": bool(claim.owner_confirmed),
                "finder_confirmed": bool(claim.finder_confirmed),
                "desk_received": bool(claim.desk_received),
                "desk_released": bool(claim.desk_released),
                "notify_message": claim.notify_message,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
                **_serial_status_payload(
                    lost_by_id.get(claim.lost_item_id),
                    found_by_id.get(claim.found_item_id),
                ),
            }
            for claim in claims
        ],
    }


@router.post("/admin/claim/desk-receive", response_model=schemas.DeskCustodyResponse)
async def admin_desk_receive(
    body: schemas.ClaimCancelRequest,
    db: Session = Depends(get_db),
    admin: models.Users = Depends(oauth2.get_admin_user),
):
    claim = _find_claim_for_admin_cancel(
        db,
        claim_id=body.claim_id,
        found_item_id=body.found_item_id,
        lost_item_id=body.lost_item_id,
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()
    message = _mark_desk_received(db, claim, found, lost)
    return {
        "claim_id": claim.id,
        "status": claim.status,
        "desk_received": bool(claim.desk_received),
        "desk_released": bool(claim.desk_released),
        "message": message,
        "processed": claim.status == "processed",
    }


@router.post("/admin/claim/desk-release", response_model=schemas.DeskCustodyResponse)
async def admin_desk_release(
    body: schemas.ClaimCancelRequest,
    db: Session = Depends(get_db),
    admin: models.Users = Depends(oauth2.get_admin_user),
):
    claim = _find_claim_for_admin_cancel(
        db,
        claim_id=body.claim_id,
        found_item_id=body.found_item_id,
        lost_item_id=body.lost_item_id,
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    found = db.query(models.FoundItem).filter(models.FoundItem.id == claim.found_item_id).first()
    lost = db.query(models.LostItem).filter(models.LostItem.id == claim.lost_item_id).first()
    message = _mark_desk_released(db, claim, found, lost)
    return {
        "claim_id": claim.id,
        "status": claim.status,
        "desk_received": bool(claim.desk_received),
        "desk_released": bool(claim.desk_released),
        "message": message,
        "processed": claim.status == "processed",
    }


@router.post("/admin/claim/cancel", response_model=schemas.ClaimCancelResponse)
async def admin_cancel_claim(
    body: schemas.ClaimCancelRequest,
    db: Session = Depends(get_db),
    admin: models.Users = Depends(oauth2.get_admin_user),
):
    claim = _find_claim_for_admin_cancel(
        db,
        claim_id=body.claim_id,
        found_item_id=body.found_item_id,
        lost_item_id=body.lost_item_id,
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status not in ("in_process", "at_desk"):
        raise HTTPException(status_code=409, detail="Only active exchanges can be cancelled")

    found, lost = _reopen_items_for_claim(db, claim)
    claim.status = "cancelled"
    db.commit()

    cancelled_by = short_name(admin.email, admin.full_name) or admin.email or "admin"
    category = (found.category if found else None) or (lost.category if lost else None) or "item"
    owner_email = normalize_email(claim.claimed_by_email or (lost.email if lost else None))
    finder_email = normalize_email(found.finder_email if found else None)
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
        "message": "Exchange cancelled by admin. Both items are open again for matching.",
        "found_status": found.status if found else None,
        "lost_status": lost.status if lost else None,
    }


@router.delete("/me/{kind}/{item_id}", response_model=schemas.AdminDeleteResponse)
async def delete_own_item(
    kind: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    kind = (kind or "").strip().lower()
    if kind not in {"lost", "found"}:
        raise HTTPException(status_code=400, detail="kind must be lost or found")

    if kind == "lost":
        item = db.query(models.LostItem).filter(models.LostItem.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Lost item not found")
        if not user_owns_lost(current_user, item):
            raise HTTPException(status_code=403, detail="You can only delete your own lost reports")
        if item.status == "in_process":
            raise HTTPException(
                status_code=409,
                detail="Cancel the in-process exchange first, then delete this report",
            )
        _delete_lost_item(db, item)
        return {
            "ok": True,
            "kind": kind,
            "id": item_id,
            "message": "Lost report deleted.",
        }

    item = db.query(models.FoundItem).filter(models.FoundItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Found item not found")
    if not user_owns_found(current_user, item):
        raise HTTPException(status_code=403, detail="You can only delete your own found reports")
    if item.status == "in_process":
        raise HTTPException(
            status_code=409,
            detail="Cancel the in-process exchange first, then delete this report",
        )
    _delete_found_item(db, item)
    return {
        "ok": True,
        "kind": kind,
        "id": item_id,
        "message": "Found report deleted.",
    }


@router.post("/me/lost/{item_id}/search-again", response_model=schemas.LostItemResponse)
async def search_again_lost(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    lost = db.query(models.LostItem).filter(models.LostItem.id == item_id).first()
    if not lost:
        raise HTTPException(status_code=404, detail="Lost item not found")
    if not user_owns_lost(current_user, lost):
        raise HTTPException(status_code=403, detail="You can only search again on your own lost reports")
    if lost.status != "open":
        raise HTTPException(
            status_code=409,
            detail="Search again is only available for open lost reports (not in process or processed)",
        )
    if as_vec(lost.text_embedding) is None:
        raise HTTPException(status_code=400, detail="This lost report has no searchable embedding")

    ranked_matches, total = rank_found_matches_for_lost(db, lost, apply_location_boost=True)
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
        "id": lost.id,
        "matches": ranked_matches,
        "total_compared": total,
        "category_searched": lost.category,
        "location_scope": f"Preferring: {lost.location}" if lost.location else None,
        "search_all_locations": False,
        "scores_breakdown": top_breakdown,
        "lost_image_url": f"/uploads/{lost.image_path}" if lost.image_path else None,
        "lost_description": lost.description,
        "lost_category": lost.category,
        "lost_location": lost.location,
        "lost_date": lost.date_lost,
    }


@router.post("/me/found/{item_id}/search-again", response_model=schemas.FoundItemResponse)
async def search_again_found(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(require_user),
):
    found = db.query(models.FoundItem).filter(models.FoundItem.id == item_id).first()
    if not found:
        raise HTTPException(status_code=404, detail="Found item not found")
    if not user_owns_found(current_user, found):
        raise HTTPException(status_code=403, detail="You can only search again on your own found reports")
    if found.status != "available":
        raise HTTPException(
            status_code=409,
            detail="Search again is only available for available found reports (not in process or processed)",
        )

    ranked_matches, total = rank_lost_matches_for_found(db, found)
    top_breakdown = (
        ranked_matches[0]["scores_breakdown"]
        if ranked_matches
        else {
            "text_to_image": None,
            "image_to_image": None,
            "found_text_to_lost_image": None,
        }
    )
    message = "No new matches for this found report."
    if ranked_matches:
        message = f"{len(ranked_matches)} possible lost report(s) matched — review and accept if correct."
    return {
        "id": found.id,
        "message": message,
        "category": found.category,
        "embedding_stored": True,
        "matches": ranked_matches,
        "total_compared": total,
        "scores_breakdown": top_breakdown,
        "found_image_url": f"/uploads/{found.image_path}" if found.image_path else None,
        "found_description": found.description,
        "found_location": found.location,
        "found_date": found.date_found,
    }


@router.post("/admin/reembed", response_model=schemas.ReembedResponse)
async def admin_reembed_items(
    db: Session = Depends(get_db),
    _admin: models.Users = Depends(oauth2.get_admin_user),
):
    """Regenerate CLIP embeddings for all lost/found rows (use after loading FT weights)."""
    lost_updated = found_updated = lost_skipped = found_skipped = 0

    for item in db.query(models.LostItem).all():
        changed = False
        if item.image_path:
            path = UPLOAD_DIR / item.image_path
            if path.is_file():
                try:
                    item.image_embedding = encode_pil_image(Image.open(path))
                    changed = True
                except Exception:
                    lost_skipped += 1
            else:
                lost_skipped += 1
        if item.description:
            try:
                item.text_embedding = encode_text(item.description)
                changed = True
            except Exception:
                lost_skipped += 1
        if changed:
            lost_updated += 1

    for item in db.query(models.FoundItem).all():
        changed = False
        if item.image_path:
            path = UPLOAD_DIR / item.image_path
            if path.is_file():
                try:
                    item.image_embedding = encode_pil_image(Image.open(path))
                    changed = True
                except Exception:
                    found_skipped += 1
            else:
                found_skipped += 1
        if item.description:
            try:
                item.text_embedding = encode_text(item.description)
                changed = True
            except Exception:
                found_skipped += 1
        if changed:
            found_updated += 1

    db.commit()
    return {
        "ok": True,
        "lost_updated": lost_updated,
        "found_updated": found_updated,
        "lost_skipped": lost_skipped,
        "found_skipped": found_skipped,
        "message": (
            f"Re-embedded {lost_updated} lost and {found_updated} found items "
            f"(skipped issues: lost={lost_skipped}, found={found_skipped})."
        ),
    }


@router.delete("/admin/{kind}/{item_id}", response_model=schemas.AdminDeleteResponse)
async def admin_delete_entry(
    kind: str,
    item_id: str,
    db: Session = Depends(get_db),
    _admin: models.Users = Depends(oauth2.get_admin_user),
):
    kind = (kind or "").strip().lower()
    if kind not in {"lost", "found", "claim"}:
        raise HTTPException(status_code=400, detail="kind must be lost, found, or claim")

    if kind == "claim":
        claim = db.query(models.Claim).filter(models.Claim.id == item_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.status == "in_process" or claim.status == "at_desk":
            _reopen_items_for_claim(db, claim)
        db.delete(claim)
        db.commit()
        return {
            "ok": True,
            "kind": kind,
            "id": item_id,
            "message": "Claim deleted.",
        }

    if kind == "lost":
        item = db.query(models.LostItem).filter(models.LostItem.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Lost item not found")
        _delete_lost_item(db, item)
        return {
            "ok": True,
            "kind": kind,
            "id": item_id,
            "message": "Lost item deleted.",
        }

    item = db.query(models.FoundItem).filter(models.FoundItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Found item not found")
    _delete_found_item(db, item)
    return {
        "ok": True,
        "kind": kind,
        "id": item_id,
        "message": "Found item deleted.",
    }


