from pydantic import BaseModel


class user(BaseModel):
    email: str
    password: str


class userRegister(user):
    full_name: str


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthRegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class AuthRegisterResponse(BaseModel):
    message: str
    dev_verify_url: str | None = None


class AuthVerifyResponse(BaseModel):
    message: str
    email: str


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
    matches: list["LostMatchItem"] = []
    total_compared: int = 0
    scores_breakdown: "ScoresBreakdown | None" = None
    found_image_url: str | None = None
    found_description: str | None = None
    found_location: str | None = None
    found_date: str | None = None


class ScoresBreakdown(BaseModel):
    text_to_image: float | None = None
    image_to_image: float | None = None
    found_text_to_lost_image: float | None = None
    text_to_text: float | None = None


class MatchItem(BaseModel):
    id: str
    score: float
    rank: int
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


class LostMatchItem(BaseModel):
    """Open lost report that may match a newly reported found item."""
    id: str
    score: float
    rank: int
    category: str
    description: str | None = None
    location: str | None = None
    date_lost: str | None = None
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
    lost_image_url: str | None = None
    lost_description: str | None = None
    lost_category: str | None = None
    lost_location: str | None = None
    lost_date: str | None = None


class ClaimRequest(BaseModel):
    found_item_id: str
    lost_item_id: str
    email: str | None = None
    # owner = lost reporter claims a found item (classic flow)
    # finder = found reporter accepts an open lost match (reverse flow)
    initiated_by: str = "owner"


class ClaimResponse(BaseModel):
    id: str
    status: str
    message: str
    notify_message: str
    # Shared only after a successful claim pairing.
    owner_email: str | None = None
    finder_email: str | None = None
    finder_name: str | None = None
    category: str | None = None
    found_location: str | None = None
    lost_location: str | None = None
    pickup_point: str = "Library Information Desk"
    mail_mode: str | None = None
    owner_mail_sent: bool = False
    finder_mail_sent: bool = False
    owner_confirmed: bool = False
    finder_confirmed: bool = False
    owner_confirm_url: str | None = None
    finder_confirm_url: str | None = None
    exchange_status: str | None = None


class ExchangeConfirmRequest(BaseModel):
    token: str


class ExchangeConfirmResponse(BaseModel):
    claim_id: str
    role: str
    status: str
    owner_confirmed: bool
    finder_confirmed: bool
    message: str
    category: str | None = None
    processed: bool = False


class ClaimConfirmAuthRequest(BaseModel):
    claim_id: str


class ClaimCancelRequest(BaseModel):
    claim_id: str | None = None
    found_item_id: str | None = None
    lost_item_id: str | None = None
    email: str | None = None


class ClaimCancelResponse(BaseModel):
    claim_id: str
    status: str
    message: str
    found_status: str | None = None
    lost_status: str | None = None


class DashboardClaim(BaseModel):
    id: str
    found_item_id: str
    lost_item_id: str
    status: str
    role: str  # owner | finder | participant
    owner_confirmed: bool = False
    finder_confirmed: bool = False
    category: str | None = None
    counterpart_email: str | None = None
    found_location: str | None = None
    lost_location: str | None = None
    can_cancel: bool = False
    created_at: str | None = None


class DashboardResponse(BaseModel):
    email: str
    lost_items: list["LostItemAdmin"]
    found_items: list["FoundItemAdmin"]
    claims: list[DashboardClaim]


class ContactEmailRequest(BaseModel):
    found_item_id: str
    lost_item_id: str
    email: str | None = None


class ContactEmailResponse(BaseModel):
    message: str
    mail_mode: str
    owner_mail_sent: bool
    finder_mail_sent: bool
    owner_email: str | None = None
    finder_email: str | None = None
    finder_name: str | None = None
    category: str | None = None
    found_location: str | None = None
    lost_location: str | None = None
    pickup_point: str = "Library Information Desk"
    notify_message: str | None = None


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
    owner_confirmed: bool = False
    finder_confirmed: bool = False
    notify_message: str | None
    created_at: str | None = None


class AdminQueueResponse(BaseModel):
    found_items: list[FoundItemAdmin]
    lost_items: list[LostItemAdmin]
    claims: list[ClaimAdmin]
