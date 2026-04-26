from app.repositories.schedule_repo import schedule_repo
from app.services.car_service import car_service
from app.schemas.schedule import ScheduleCreate, ScheduleStatusUpdate
from app.models.user import User
from fastapi import HTTPException
from beanie import PydanticObjectId
from datetime import datetime, timezone, timedelta

class ScheduleService:
    async def create_schedule(self, user: User, schedule_in: ScheduleCreate):
        # Business rule: max 2 pending appointments
        pending_count = await schedule_repo.count_pending_for_user(user.id)
        if pending_count >= 2:
            raise HTTPException(status_code=400, detail="Maximum 2 pending appointments allowed")

        # Business rule: date must be at least today + 1
        now = datetime.now(timezone.utc)
        min_date = now + timedelta(days=1)
        if schedule_in.date.replace(tzinfo=timezone.utc) < min_date:
            raise HTTPException(status_code=400, detail="Appointment date must be at least 24 hours from now")

        # Verify car exists
        car = await car_service.get_car(schedule_in.car_id)
        
        data = {
            "user_id": user.id,
            "car_id": car.id,
            "date": schedule_in.date,
            "status": "pending"
        }
        return await schedule_repo.create(data)

    async def get_my_schedules(self, user: User, page: int, limit: int):
        skip = (page - 1) * limit
        schedules, total = await schedule_repo.get_by_user(user.id, skip=skip, limit=limit)
        return schedules, total

    async def get_all_schedules(self, page: int, limit: int):
        skip = (page - 1) * limit
        schedules = await schedule_repo.get_all(skip=skip, limit=limit)
        # Using beanie to count all
        total = await schedule_repo.model.find_all().count()
        return schedules, total

    async def get_schedule(self, schedule_id: str):
        try:
            schedule = await schedule_repo.get(PydanticObjectId(schedule_id))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID format")
            
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return schedule

    async def cancel_schedule(self, user: User, schedule_id: str):
        schedule = await self.get_schedule(schedule_id)
        if schedule.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if schedule.status != "pending":
            raise HTTPException(status_code=400, detail="Only pending schedules can be cancelled")
            
        schedule.status = "cancelled"
        await schedule.save()
        return schedule

    async def update_status(self, schedule_id: str, status_update: ScheduleStatusUpdate):
        schedule = await self.get_schedule(schedule_id)
        valid_statuses = ["pending", "confirmed", "cancelled", "completed"]
        if status_update.status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
            
        schedule.status = status_update.status
        await schedule.save()
        return schedule

    async def delete_schedule(self, user: User, schedule_id: str):
        schedule = await self.get_schedule(schedule_id)
        if schedule.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        await schedule_repo.delete(schedule.id)
        return True

schedule_service = ScheduleService()
