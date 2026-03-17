from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


EntityType = Literal["drug", "herb"]
Severity = Literal["high", "medium"]
SummaryLevel = Literal["danger", "warning", "safe"]
ThemeType = Literal["light", "dark"]
ChatRole = Literal["user", "assistant"]
OrchestratorType = Literal["gemini", "local"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "HerbaGuard API"


class SearchResult(BaseModel):
    type: EntityType
    id: int
    canonical_name: str
    matched_alias: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)


class CheckInteractionRequest(BaseModel):
    items: list[str] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def validate_items(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if isinstance(item, str) and item.strip()]
        if len(cleaned) < 2:
            raise ValueError("Cần cung cấp ít nhất 2 mục hợp lệ.")
        return cleaned


class ResolvedItem(BaseModel):
    input: str
    type: EntityType
    id: int
    canonical_name: str
    matched_alias: str
    confidence: float


class InteractionDetail(BaseModel):
    mechanism: str
    possible_consequences: list[str] = Field(default_factory=list)
    recommendation: str


class InteractionEntityRef(BaseModel):
    id: int
    canonical_name: str


class InteractionPair(BaseModel):
    drug: InteractionEntityRef
    herb: InteractionEntityRef
    severity: Severity
    interaction: InteractionDetail


class Summary(BaseModel):
    level: SummaryLevel
    title: str
    message: str
    recommendation: str


class CheckInteractionResponse(BaseModel):
    success: bool = True
    input_items: list[str]
    resolved_items: list[ResolvedItem] = Field(default_factory=list)
    interaction_found: bool = False
    interaction_pairs: list[InteractionPair] = Field(default_factory=list)
    summary: Summary
    unresolved_items: list[str] = Field(default_factory=list)


class AuthUser(BaseModel):
    id: int
    full_name: str
    email: str


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Email không hợp lệ.")
        return normalized

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Họ tên không hợp lệ.")
        return cleaned


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Email không hợp lệ.")
        return normalized


class AuthResponse(BaseModel):
    success: bool = True
    message: str
    token: str
    user: AuthUser


class MedicineUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    dosage: str = Field(default="", max_length=120)
    instructions: str = Field(default="", max_length=300)
    stock_count: int = Field(default=0, ge=0, le=10000)
    kind: Literal["drug", "herb", "unknown"] = "unknown"

    @field_validator("name", "dosage", "instructions")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class MedicineItem(BaseModel):
    id: int
    name: str
    dosage: str
    instructions: str
    stock_count: int
    kind: Literal["drug", "herb", "unknown"]
    created_at: str
    updated_at: str


class ReminderUpsertRequest(BaseModel):
    medicine_id: int = Field(..., ge=1)
    time_of_day: str = Field(..., min_length=4, max_length=5)
    frequency_note: str = Field(default="Hằng ngày", max_length=120)
    meal_note: str = Field(default="", max_length=120)
    is_enabled: bool = True

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, value: str) -> str:
        cleaned = value.strip()
        parts = cleaned.split(":")
        if len(parts) != 2:
            raise ValueError("Định dạng giờ không hợp lệ. Ví dụ: 08:30")

        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise ValueError("Định dạng giờ không hợp lệ. Ví dụ: 08:30") from exc

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Giờ nhắc không hợp lệ.")

        return f"{hour:02d}:{minute:02d}"

    @field_validator("frequency_note", "meal_note")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()


class ReminderItem(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    time_of_day: str
    frequency_note: str
    meal_note: str
    is_enabled: bool
    next_due_iso: str
    created_at: str
    updated_at: str


class UserSettings(BaseModel):
    voice_enabled: bool = False
    large_text: bool = False
    theme: ThemeType = "light"
    browser_notifications: bool = False


class SettingsUpdateRequest(BaseModel):
    voice_enabled: bool | None = None
    large_text: bool | None = None
    theme: ThemeType | None = None
    browser_notifications: bool | None = None


class DashboardAlert(BaseModel):
    type: Literal["low_stock", "interaction", "reminder"]
    title: str
    message: str
    action_label: str = ""


class DashboardData(BaseModel):
    alerts: list[DashboardAlert] = Field(default_factory=list)
    upcoming_reminders: list[ReminderItem] = Field(default_factory=list)
    low_stock_medicines: list[MedicineItem] = Field(default_factory=list)


class CheckHistoryItem(BaseModel):
    id: int
    input_items: list[str]
    summary_level: SummaryLevel
    summary_title: str
    created_at: str


class ChatHistoryMessage(BaseModel):
    role: ChatRole
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=80)
    history: list[ChatHistoryMessage] = Field(default_factory=list)

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class GroundingEntity(BaseModel):
    type: EntityType
    id: int
    name: str


class GroundingInteraction(BaseModel):
    drug_id: int
    herb_id: int
    drug_name: str
    herb_name: str
    severity: Severity
    mechanism: str
    possible_consequences: list[str] = Field(default_factory=list)
    recommendation: str


class ChatGrounding(BaseModel):
    entities: list[GroundingEntity] = Field(default_factory=list)
    interactions: list[GroundingInteraction] = Field(default_factory=list)
    interaction_found: bool | None = None
    evidence: InteractionDetail | None = None


class ChatResponse(BaseModel):
    success: bool = True
    answer: str
    grounding: ChatGrounding
    citations: list[str] = Field(default_factory=list)
    fallback: bool = False
    orchestrator: OrchestratorType = "local"
    session_id: str | None = None
    used_memory: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatStoredMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime
    grounding: ChatGrounding | None = None
    citations: list[str] = Field(default_factory=list)
    fallback: bool | None = None


class ChatHistoryResponse(BaseModel):
    success: bool = True
    session_id: str
    messages: list[ChatStoredMessage] = Field(default_factory=list)


class ChatHistoryClearResponse(BaseModel):
    success: bool = True
    session_id: str
    deleted_count: int = 0
