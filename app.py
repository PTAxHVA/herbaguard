from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import load_config
from database.mongo import get_mongo_database
from models import (
    AuthResponse,
    AuthUser,
    ChatHistoryClearResponse,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    ChatStoredMessage,
    CheckHistoryItem,
    CheckInteractionRequest,
    CheckInteractionResponse,
    DashboardData,
    HealthResponse,
    LoginRequest,
    MedicineItem,
    MedicineUpsertRequest,
    RegisterRequest,
    ReminderItem,
    ReminderUpsertRequest,
    SearchResponse,
    SearchResult,
    SettingsUpdateRequest,
    UserSettings,
)
from services.auth_service import AuthService
from services.chat_memory_service import ChatMemoryService
from services.chat_service import ChatService
from services.data_loader import load_database
from services.graph_service import KnowledgeGraphService
from services.interaction_service import InteractionService
from services.normalize import deduplicate_inputs
from services.resolver import EntityResolver
from services.user_data_service import UserDataService

_CONFIG = load_config()
if not _CONFIG.static_dir.exists():
    raise RuntimeError(f"Không tìm thấy thư mục frontend: {_CONFIG.static_dir}")

_MONGO_DB = get_mongo_database(
    _CONFIG.mongodb_uri,
    _CONFIG.mongodb_db_name,
    use_mock=_CONFIG.mongodb_use_mock,
)

_DATABASE = load_database(_CONFIG.project_root)
_RESOLVER = EntityResolver(_DATABASE)
_INTERACTION_SERVICE = InteractionService(_DATABASE, _RESOLVER)
_GRAPH_SERVICE = KnowledgeGraphService(_DATABASE, _RESOLVER)
_CHAT_MEMORY_SERVICE = ChatMemoryService(_MONGO_DB)
_CHAT_SERVICE = ChatService(_GRAPH_SERVICE, memory_service=_CHAT_MEMORY_SERVICE)
_AUTH_SERVICE = AuthService(_MONGO_DB)
_USER_DATA_SERVICE = UserDataService(_MONGO_DB)


app = FastAPI(
    title="HerbaGuard",
    version="3.0.0",
    description="Vietnamese local-first herb-drug interaction assistant.",
)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _require_authenticated_user(authorization: str | None) -> AuthUser:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Thiếu token đăng nhập.")

    user = _AUTH_SERVICE.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")

    return AuthUser(id=user.id, full_name=user.full_name, email=user.email)


def _optional_user_id(authorization: str | None) -> str | None:
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    user = _AUTH_SERVICE.get_user_by_token(token)
    if user is None:
        return None
    return user.id


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest) -> AuthResponse:
    try:
        user, token = _AUTH_SERVICE.register(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AuthResponse(
        success=True,
        message="Đăng ký thành công.",
        token=token,
        user=AuthUser(id=user.id, full_name=user.full_name, email=user.email),
    )


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    try:
        user, token = _AUTH_SERVICE.login(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return AuthResponse(
        success=True,
        message="Đăng nhập thành công.",
        token=token,
        user=AuthUser(id=user.id, full_name=user.full_name, email=user.email),
    )


@app.get("/api/auth/me", response_model=AuthUser)
def me(authorization: str | None = Header(default=None)) -> AuthUser:
    return _require_authenticated_user(authorization)


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    token = _extract_bearer_token(authorization)
    if token:
        _AUTH_SERVICE.logout(token)
    return {"success": True}


@app.get("/api/settings", response_model=UserSettings)
def get_settings(authorization: str | None = Header(default=None)) -> UserSettings:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.get_settings(user.id)


@app.put("/api/settings", response_model=UserSettings)
def update_settings(payload: SettingsUpdateRequest, authorization: str | None = Header(default=None)) -> UserSettings:
    user = _require_authenticated_user(authorization)
    updates = payload.model_dump(exclude_unset=True)
    return _USER_DATA_SERVICE.update_settings(user.id, updates)


@app.get("/api/dashboard", response_model=DashboardData)
def get_dashboard(authorization: str | None = Header(default=None)) -> DashboardData:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.get_dashboard_data(user.id)


@app.get("/api/medicines", response_model=list[MedicineItem])
def list_medicines(authorization: str | None = Header(default=None)) -> list[MedicineItem]:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.list_medicines(user.id)


@app.post("/api/medicines", response_model=MedicineItem)
def create_medicine(payload: MedicineUpsertRequest, authorization: str | None = Header(default=None)) -> MedicineItem:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.create_medicine(
        user.id,
        name=payload.name,
        dosage=payload.dosage,
        instructions=payload.instructions,
        stock_count=payload.stock_count,
        kind=payload.kind,
    )


@app.put("/api/medicines/{medicine_id}", response_model=MedicineItem)
def update_medicine(
    medicine_id: str,
    payload: MedicineUpsertRequest,
    authorization: str | None = Header(default=None),
) -> MedicineItem:
    user = _require_authenticated_user(authorization)
    try:
        row = _USER_DATA_SERVICE.update_medicine(
            user.id,
            medicine_id,
            name=payload.name,
            dosage=payload.dosage,
            instructions=payload.instructions,
            stock_count=payload.stock_count,
            kind=payload.kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thuốc cần cập nhật.")
    return row


@app.delete("/api/medicines/{medicine_id}")
def delete_medicine(medicine_id: str, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    user = _require_authenticated_user(authorization)
    try:
        deleted = _USER_DATA_SERVICE.delete_medicine(user.id, medicine_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy thuốc cần xóa.")
    return {"success": True}


@app.get("/api/reminders", response_model=list[ReminderItem])
def list_reminders(authorization: str | None = Header(default=None)) -> list[ReminderItem]:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.list_reminders(user.id)


@app.post("/api/reminders", response_model=ReminderItem)
def create_reminder(payload: ReminderUpsertRequest, authorization: str | None = Header(default=None)) -> ReminderItem:
    user = _require_authenticated_user(authorization)
    try:
        return _USER_DATA_SERVICE.create_reminder(
            user.id,
            medicine_id=payload.medicine_id,
            time_of_day=payload.time_of_day,
            frequency_note=payload.frequency_note,
            meal_note=payload.meal_note,
            is_enabled=payload.is_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/reminders/{reminder_id}", response_model=ReminderItem)
def update_reminder(
    reminder_id: str,
    payload: ReminderUpsertRequest,
    authorization: str | None = Header(default=None),
) -> ReminderItem:
    user = _require_authenticated_user(authorization)
    try:
        row = _USER_DATA_SERVICE.update_reminder(
            user.id,
            reminder_id,
            medicine_id=payload.medicine_id,
            time_of_day=payload.time_of_day,
            frequency_note=payload.frequency_note,
            meal_note=payload.meal_note,
            is_enabled=payload.is_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch nhắc cần cập nhật.")
    return row


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    user = _require_authenticated_user(authorization)
    try:
        deleted = _USER_DATA_SERVICE.delete_reminder(user.id, reminder_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch nhắc cần xóa.")
    return {"success": True}


@app.get("/api/check-history", response_model=list[CheckHistoryItem])
def list_check_history(
    limit: int = Query(default=10, ge=1, le=50),
    authorization: str | None = Header(default=None),
) -> list[CheckHistoryItem]:
    user = _require_authenticated_user(authorization)
    return _USER_DATA_SERVICE.list_check_history(user.id, limit=limit)


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(10, ge=1, le=20),
) -> SearchResponse:
    results = _RESOLVER.search(q, limit=limit)
    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                type=item.entity_type,
                id=item.entity_id,
                canonical_name=item.canonical_name,
                matched_alias=item.matched_alias,
            )
            for item in results
        ],
    )


@app.post("/api/check-interaction", response_model=CheckInteractionResponse)
def check_interaction(
    payload: CheckInteractionRequest,
    authorization: str | None = Header(default=None),
) -> CheckInteractionResponse:
    unique_items = deduplicate_inputs(payload.items)
    if len(unique_items) < 2:
        raise HTTPException(status_code=400, detail="Vui lòng nhập ít nhất 2 mục khác nhau để kiểm tra.")

    result = _INTERACTION_SERVICE.check_interactions(payload.items)

    user_id = _optional_user_id(authorization)
    if user_id is not None:
        _USER_DATA_SERVICE.add_check_history(
            user_id,
            input_items=result.input_items,
            summary_level=result.summary.level,
            summary_title=result.summary.title,
            result_payload=result.model_dump(),
        )

    return result


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, authorization: str | None = Header(default=None)) -> ChatResponse:
    user = _require_authenticated_user(authorization)
    session_id = _CHAT_MEMORY_SERVICE.ensure_session_id(payload.session_id)
    return _CHAT_SERVICE.chat_with_memory(
        user_id=user.id,
        session_id=session_id,
        message=payload.message,
        history=payload.history,
    )


@app.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(
    session_id: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(default=80, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> ChatHistoryResponse:
    user = _require_authenticated_user(authorization)
    normalized_session = _CHAT_MEMORY_SERVICE.ensure_session_id(session_id)
    rows = _CHAT_SERVICE.get_history(user_id=user.id, session_id=normalized_session, limit=limit)
    return ChatHistoryResponse(
        session_id=normalized_session,
        messages=[
            ChatStoredMessage(
                role=row.role,
                content=row.content,
                created_at=row.created_at,
                grounding=row.grounding,
                citations=row.citations,
                fallback=row.fallback,
            )
            for row in rows
        ],
    )


@app.delete("/api/chat/history", response_model=ChatHistoryClearResponse)
def clear_chat_history(
    session_id: str = Query(..., min_length=1, max_length=80),
    authorization: str | None = Header(default=None),
) -> ChatHistoryClearResponse:
    user = _require_authenticated_user(authorization)
    normalized_session = _CHAT_MEMORY_SERVICE.ensure_session_id(session_id)
    deleted_count = _CHAT_SERVICE.clear_history(user_id=user.id, session_id=normalized_session)
    return ChatHistoryClearResponse(session_id=normalized_session, deleted_count=deleted_count)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_CONFIG.static_dir / "index.html")


app.mount("/", StaticFiles(directory=str(_CONFIG.static_dir), html=True), name="frontend")
