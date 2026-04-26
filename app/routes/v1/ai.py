from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import List, Any
from app.schemas.common import ResponseModel
from app.ai.chat import ai_chat_service
from app.core.config import settings
from app.services.car_service import car_service

router = APIRouter(prefix="/ai", tags=["ai"])

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatData(BaseModel):
    reply: str
    car_recommendations: List[Any]
    action: Any = None

@router.post("/chat", response_model=ResponseModel[ChatData])
async def chat(request: ChatRequest):
    result = await ai_chat_service.get_response(request.message)
    return ResponseModel(data=result, message="Chat processed")

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def verify_internal_token(api_key_header: str = Security(api_key_header)):
    if api_key_header == f"Bearer {settings.INTERNAL_SERVICE_TOKEN}":
        return True
    raise HTTPException(status_code=403, detail="Invalid internal token")

@router.get("/inventory-search", response_model=ResponseModel[List[Any]])
async def internal_inventory_search(
    brand: str = None,
    min_price: float = None,
    max_price: float = None,
    status: str = None,
    token: bool = Depends(verify_internal_token)
):
    cars, _ = await car_service.get_all_cars(
        page=1, limit=50, brand=brand, min_price=min_price, max_price=max_price, status=status
    )
    data = [{"id": str(c.id), "brand": c.brand, "type": c.type, "price": c.price} for c in cars]
    return ResponseModel(data=data, message="Inventory retrieved")
