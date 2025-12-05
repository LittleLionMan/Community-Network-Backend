from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.availability import (
    AvailabilitySlotCreate,
    AvailabilitySlotPublic,
    AvailabilitySlotRead,
    AvailabilitySlotUpdate,
)
from app.services.availability_service import AvailabilityService

router = APIRouter()


@router.post(
    "/my", response_model=AvailabilitySlotRead, status_code=status.HTTP_201_CREATED
)
async def create_availability_slot(
    slot_data: AvailabilitySlotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvailabilitySlotRead:
    slot_dict = slot_data.model_dump(exclude_unset=True)
    slot_dict["source"] = "manual"

    slot = await AvailabilityService.create_slot(
        db=db,
        user_id=current_user.id,
        slot_data=slot_dict,
    )

    return AvailabilitySlotRead.model_validate(slot)


@router.get("/my", response_model=list[AvailabilitySlotRead])
async def get_my_availability_slots(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AvailabilitySlotRead]:
    slots = await AvailabilityService.get_user_slots(
        db=db,
        user_id=current_user.id,
        include_inactive=include_inactive,
    )

    return [AvailabilitySlotRead.model_validate(slot) for slot in slots]


@router.patch("/my/{slot_id}", response_model=AvailabilitySlotRead)
async def update_availability_slot(
    slot_id: int,
    update_data: AvailabilitySlotUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AvailabilitySlotRead:
    slot = await AvailabilityService.get_slot_by_id(
        db=db,
        slot_id=slot_id,
        user_id=current_user.id,
    )

    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Availability slot not found"
        )

    if slot.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify automatically created slots",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    updated_slot = await AvailabilityService.update_slot(
        db=db,
        slot=slot,
        update_data=update_dict,
    )

    return AvailabilitySlotRead.model_validate(updated_slot)


@router.delete("/my/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_availability_slot(
    slot_id: int,
    hard_delete: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    slot = await AvailabilityService.get_slot_by_id(
        db=db,
        slot_id=slot_id,
        user_id=current_user.id,
    )

    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Availability slot not found"
        )

    if slot.source != "manual" and not hard_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete automatically created slots without hard_delete=true",
        )

    await AvailabilityService.delete_slot(
        db=db,
        slot=slot,
        soft_delete=not hard_delete,
    )


@router.get("/users/{user_id}", response_model=list[AvailabilitySlotPublic])
async def get_user_public_availability(
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AvailabilitySlotPublic]:
    slots = await AvailabilityService.get_public_availability(
        db=db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    return [
        AvailabilitySlotPublic(
            slot_type=slot.slot_type,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            specific_date=slot.specific_date,
            specific_start=slot.specific_start,
            specific_end=slot.specific_end,
            display_label=slot.title if slot.slot_type == "blocked" else None,
        )
        for slot in slots
    ]
