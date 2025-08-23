from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.service import Service
from app.models.user import User
from app.schemas.service import (
    ServiceCreate, ServiceRead, ServiceUpdate, ServiceSummary
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_current_admin_user, get_optional_current_user

router = APIRouter()

@router.get(
    "/",
    response_model=List[ServiceSummary],
    summary="Get all services",
    description="Public endpoint to retrieve all active services with pagination and filters"
)
async def get_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_offering: Optional[bool] = Query(None, description="Filter by offering/seeking"),
    search: Optional[str] = Query(None, min_length=3, description="Search in title and description"),
    db: AsyncSession = Depends(get_db)
):
    """Get all services (public endpoint with filters)"""
    query = select(Service).where(Service.is_active == True)

    if is_offering is not None:
        query = query.where(Service.is_offering == is_offering)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            Service.title.ilike(search_term) |
            Service.description.ilike(search_term)
        )

    query = query.order_by(Service.created_at.desc()).offset(skip).limit(limit)

    query = query.options(selectinload(Service.user))

    result = await db.execute(query)
    services = result.scalars().all()

    return [ServiceSummary.model_validate(service) for service in services]

@router.get(
    "/{service_id}",
    response_model=ServiceRead,
    responses={
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def get_service(
    service_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get specific service details"""
    query = select(Service).where(
        Service.id == service_id,
        Service.is_active == True
    ).options(selectinload(Service.user))

    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    return ServiceRead.model_validate(service)

@router.post(
    "/",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid service data"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def create_service(
    service_data: ServiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service_dict = service_data.model_dump()
    service_dict["user_id"] = current_user.id

    db_service = Service(**service_dict)
    db.add(db_service)
    await db.commit()
    await db.refresh(db_service, ["user"])

    return ServiceRead.model_validate(db_service)

@router.put(
    "/{service_id}",
    response_model=ServiceRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid service data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this service"},
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.id == service_id, Service.is_active == True)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this service"
        )

    update_data = service_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service, ["user"])

    return ServiceRead.model_validate(service)

@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to delete this service"},
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def delete_service(
    service_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.id == service_id, Service.is_active == True)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this service"
        )

    service.is_active = False
    await db.commit()

@router.get(
    "/my/",
    response_model=List[ServiceSummary],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_offering: Optional[bool] = Query(None, description="Filter by offering/seeking"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Service).where(
        Service.user_id == current_user.id,
        Service.is_active == True
    )

    if is_offering is not None:
        query = query.where(Service.is_offering == is_offering)

    query = query.options(selectinload(Service.user)).order_by(
        Service.created_at.desc()
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    services = result.scalars().all()

    return [ServiceSummary.model_validate(service) for service in services]

@router.get(
    "/stats",
    responses={}
)
async def get_service_stats(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.is_active == True)
    )
    services = result.scalars().all()

    total_services = len(services)
    offerings = len([s for s in services if s.is_offering])
    seekings = len([s for s in services if not s.is_offering])

    return {
        "total_active_services": total_services,
        "services_offered": offerings,
        "services_requested": seekings
    }
