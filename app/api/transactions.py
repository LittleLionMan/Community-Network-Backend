from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.exchange_transaction import TransactionStatus as ModelTransactionStatus
from app.models.user import User
from app.schemas.transaction import (
    CancelTransactionRequest,
    ConfirmHandoverRequest,
    ConfirmTimeRequest,
    ProposeTimeRequest,
    TransactionCreate,
    TransactionData,
    TransactionHistoryItem,
    UpdateAddressRequest,
)
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.post("", response_model=TransactionData, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    provider_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    if provider_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot create transaction with yourself"
        )

    service = TransactionService(db)
    return await service.create_transaction(
        requester_id=current_user.id,
        provider_id=provider_id,
        conversation_id=0,
        data=data,
    )


@router.get("/available-slots", response_model=dict[str, int])
async def get_available_request_slots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    service = TransactionService(db)
    return await service.get_user_available_request_slots(current_user.id)


@router.post("/{transaction_id}/propose-time", response_model=TransactionData)
async def propose_time(
    transaction_id: int,
    data: ProposeTimeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.propose_time(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/confirm-time", response_model=TransactionData)
async def confirm_time(
    transaction_id: int,
    data: ConfirmTimeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.confirm_time(transaction_id, current_user.id, data)


@router.put("/{transaction_id}/address", response_model=TransactionData)
async def update_transaction_address(
    transaction_id: int,
    data: UpdateAddressRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.update_exact_address(
        transaction_id=transaction_id,
        user_id=current_user.id,
        new_address=data.exact_address,
    )


@router.post("/{transaction_id}/confirm-handover", response_model=TransactionData)
async def confirm_handover(
    transaction_id: int,
    data: ConfirmHandoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.confirm_handover(transaction_id, current_user.id)


@router.post("/{transaction_id}/cancel", response_model=TransactionData)
async def cancel_transaction(
    transaction_id: int,
    data: CancelTransactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.cancel_transaction(transaction_id, current_user.id)


@router.get("/{transaction_id}", response_model=TransactionData)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionData:
    service = TransactionService(db)
    return await service.get_transaction(transaction_id, current_user.id)


@router.get("", response_model=list[TransactionHistoryItem])
async def get_user_transactions(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionHistoryItem]:
    service = TransactionService(db)

    status_filter = None
    if status:
        try:
            status_filter = ModelTransactionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status value. Must be one of: {', '.join(s.value for s in ModelTransactionStatus)}",
            )

    return await service.get_user_transactions(
        user_id=current_user.id,
        status_filter=status_filter,
        limit=limit,
    )
