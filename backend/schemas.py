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


class ScoresBreakdown(BaseModel):
    text_to_image: float | None = None
    image_to_image: float | None = None
    found_text_to_lost_image: float | None = None


class LostItemResponse(BaseModel):
    matches: list[MatchItem]
    total_compared: int
    category_searched: str
    scores_breakdown: ScoresBreakdown