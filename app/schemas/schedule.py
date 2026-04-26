from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.schemas.car import CarResponse

class ScheduleCreate(BaseModel):
    car_id: str
    date: datetime

class ScheduleStatusUpdate(BaseModel):
    status: str

class ScheduleResponse(BaseModel):
    id: str
    user_id: str
    car_id: str
    date: datetime
    status: str
    created_at: datetime
    updated_at: datetime

class ScheduleDetailResponse(ScheduleResponse):
    car: Optional[CarResponse] = None
