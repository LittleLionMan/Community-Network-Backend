from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.exchange_transaction import TransactionStatus as ModelTransactionStatus
from app.models.user import User
from app.schemas.transaction import (
    AcceptTransactionRequest,
    CancelTransactionRequest,
    ConfirmHandoverRequest,
    ConfirmTimeRequest,
    ProposeTimeRequest,
    RejectTransactionRequest,
    TransactionCreate,
    TransactionData,
    TransactionHistoryItem,
)
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionData, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    conversation_id: int,
    provider_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.create_transaction(
        requester_id=current_user.id,
        provider_id=provider_id,
        conversation_id=conversation_id,
        data=data,
    )


@router.post("/{transaction_id}/accept", response_model=TransactionData)
async def accept_transaction(
    transaction_id: int,
    data: AcceptTransactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.accept_transaction(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/reject", response_model=TransactionData)
async def reject_transaction(
    transaction_id: int,
    data: RejectTransactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.reject_transaction(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/propose-time", response_model=TransactionData)
async def propose_time(
    transaction_id: int,
    data: ProposeTimeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.propose_time(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/confirm-time", response_model=TransactionData)
async def confirm_time(
    transaction_id: int,
    data: ConfirmTimeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.confirm_time(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/confirm-handover", response_model=TransactionData)
async def confirm_handover(
    transaction_id: int,
    data: ConfirmHandoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.confirm_handover(transaction_id, current_user.id, data)


@router.post("/{transaction_id}/cancel", response_model=TransactionData)
async def cancel_transaction(
    transaction_id: int,
    data: CancelTransactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.cancel_transaction(transaction_id, current_user.id, data)


@router.get("/{transaction_id}", response_model=TransactionData)
async def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TransactionService(db)
    return await service.get_transaction(transaction_id, current_user.id)


@router.get("", response_model=list[TransactionHistoryItem])
async def get_user_transactions(
    status: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
