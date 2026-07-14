from pydantic import BaseModel


class user(BaseModel):
    email: str
    password: str


class userRegister(user):
    full_name: str


class token(BaseModel):
    access_token: str
    token_type: str


class tokenData(BaseModel):
    id: int


class UserInDB(user):
    hashed_password: str


class CategoryPredictionResponse(BaseModel):
    predicted: str
    confidence: float
    all_scores: dict[str, float]


class FoundItemResponse(BaseModel):
    id: str
    message: str
    category: str
    embedding_stored: bool


class ScoresBreakdown(BaseModel):
    text_to_image: float | None = None
    image_to_image: float | None = None
    found_text_to_lost_image: float | None = None


class MatchItem(BaseModel):
    id: str
    score: float
    category: str
    description: str | None = None
    location: str | None = None
    date_found: str | None = None
    time_found: str | None = None
    reported_by: str | None = None
    image_url: str | None = None
    same_category: bool
    tier: str
    scores_breakdown: ScoresBreakdown


class LostItemResponse(BaseModel):
    id: str
    matches: list[MatchItem]
    total_compared: int
    category_searched: str
    scores_breakdown: ScoresBreakdown


class ClaimRequest(BaseModel):
    found_item_id: str
    lost_item_id: str
    email: str | None = None


class ClaimResponse(BaseModel):
    id: str
    status: str
    message: str
    notify_message: str


class FoundItemAdmin(BaseModel):
    id: str
    description: str | None
    category: str
    location: str | None
    date_found: str | None
    time_found: str | None
    reported_by: str | None
    finder_email: str | None
    image_url: str | None
    status: str
    created_at: str | None = None


class LostItemAdmin(BaseModel):
    id: str
    description: str
    category: str
    location: str | None
    date_lost: str | None
    email: str | None
    image_url: str | None
    status: str
    created_at: str | None = None


class ClaimAdmin(BaseModel):
    id: str
    found_item_id: str
    lost_item_id: str
    claimed_by_email: str | None
    status: str
    notify_message: str | None
    created_at: str | None = None


class AdminQueueResponse(BaseModel):
    found_items: list[FoundItemAdmin]
    lost_items: list[LostItemAdmin]
    claims: list[ClaimAdmin]
