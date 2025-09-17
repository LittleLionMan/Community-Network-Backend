from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime
import json

from app.database import get_db
from app.models.service import Service
from app.models.user import User
from app.schemas.service import (
    ServiceCreate, ServiceRead, ServiceUpdate, ServiceSummary
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_optional_current_user
from app.core.rate_limit_decorator import service_create_rate_limit, read_rate_limit
from app.services.matching_service import ServiceMatchingService
from app.services.file_service import FileUploadService

router = APIRouter()

@router.get(
    "/",
    response_model=List[ServiceSummary],
    summary="Get all services",
    description="Public endpoint to retrieve all active services with pagination and filters"
)
@read_rate_limit("service_listing")
async def get_services(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_offering: Optional[bool] = Query(None, description="Filter by offering/seeking"),
    search: Optional[str] = Query(None, min_length=3, description="Search in title and description"),
    exclude_own: bool = Query(False, description="Exclude current user's services"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Service).where(Service.is_active == True)

    if is_offering is not None:
        query = query.where(Service.is_offering == is_offering)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            Service.title.ilike(search_term) |
            Service.description.ilike(search_term)
        )

    if exclude_own and current_user:
        query = query.where(Service.user_id != current_user.id)

    query = query.order_by(Service.created_at.desc()).offset(skip).limit(limit)
    query = query.options(selectinload(Service.user))

    result = await db.execute(query)
    services = result.scalars().all()

    return [ServiceSummary.model_validate(service, from_attributes=True) for service in services]

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

    return [ServiceSummary.model_validate(service, from_attributes=True) for service in services]

@router.get("/stats")
async def get_service_stats(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(Service.is_active == True)
    )
    services = result.scalars().all()

    total_services = len(services)
    offerings = len([s for s in services if s.is_offering])
    seekings = len([s for s in services if not s.is_offering])

    if seekings == 0:
        market_balance = 100.0
    else:
        market_balance = round(offerings / seekings, 2)

    stats = {
        "total_active_services": total_services,
        "services_offered": offerings,
        "services_requested": seekings,
        "market_balance": market_balance
    }

    if current_user:
        user_services = [s for s in services if s.user_id == current_user.id]
        user_offerings = len([s for s in user_services if s.is_offering])
        user_requests = len([s for s in user_services if not s.is_offering])

        stats["user_stats"] = {
            "my_services": len(user_services),
            "my_offerings": user_offerings,
            "my_requests": user_requests
        }

    return stats

@router.get(
    "/recommendations",
    response_model=List[ServiceSummary],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_service_recommendations(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        matching_service = ServiceMatchingService(db)
        recommendations = await matching_service.find_matching_services(
            user_id=current_user.id,
            limit=limit
        )
        return [ServiceSummary.model_validate(service, from_attributes=True) for service in recommendations]
    except Exception:
        result = await db.execute(
            select(Service).where(
                and_(
                    Service.is_active == True,
                    Service.user_id != current_user.id
                )
            ).options(selectinload(Service.user))
            .order_by(Service.created_at.desc())
            .limit(limit)
        )
        services = result.scalars().all()
        return [ServiceSummary.model_validate(service, from_attributes=True) for service in services]

@router.get(
    "/{service_id}",
    response_model=ServiceRead,
    responses={
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
@read_rate_limit("service_listing")
async def get_service(
    request: Request,
    service_id: int,
    db: AsyncSession = Depends(get_db)
):
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

    return ServiceRead.model_validate(service, from_attributes=True)

@router.post(
    "/",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid service data"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
@service_create_rate_limit
async def create_service(
    request: Request,
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

    return ServiceRead.model_validate(db_service, from_attributes=True)

@router.post(
    "/with-image",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid service data"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
@service_create_rate_limit
async def create_service_with_image(
    request: Request,
    title: str = Form(..., min_length=1, max_length=100),
    description: str = Form(..., min_length=10, max_length=2000),
    is_offering: bool = Form(...),
    service_image: Optional[UploadFile] = File(None),
    meeting_locations: Optional[str] = Form(None),
    price_amount: Optional[float] = Form(None),
    estimated_duration_hours: Optional[int] = Form(None),
    response_time_hours: Optional[int] = Form(None),
    price_type: Optional[str] = Form(None),
    contact_method: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    parsed_locations = []
    if meeting_locations:
        try:
            parsed_locations = json.loads(meeting_locations)
            if not isinstance(parsed_locations, list):
                raise ValueError("Invalid format")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid meeting_locations format. Must be JSON array."
            )

    service_image_url = None
    if service_image:
        file_service = FileUploadService()
        try:
            _, public_url = await file_service.upload_service_image(service_image, current_user.id)
            service_image_url = public_url
        except HTTPException as http_exc:
            raise HTTPException(
                status_code=http_exc.status_code,
                detail={
                    "error": "image_upload_failed",
                    "message": http_exc.detail,
                    "user_message": "Das hochgeladene Bild konnte nicht verarbeitet werden. Bitte versuchen Sie es mit einem anderen Bild."
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "image_upload_error",
                    "message": str(e),
                    "user_message": "Fehler beim Hochladen des Bildes. Bitte versuchen Sie es erneut."
                }
            )

    service_dict = {
        "title": title.strip(),
        "description": description.strip(),
        "is_offering": is_offering,
        "user_id": current_user.id,
        "service_image_url": service_image_url,
        "meeting_locations": parsed_locations[:5] if parsed_locations else None,
        "price_amount": price_amount,
        "estimated_duration_hours": estimated_duration_hours,
        "response_time_hours": response_time_hours,
        "price_type": price_type,
        "contact_method": contact_method,
    }

    db_service = Service(**service_dict)
    db.add(db_service)
    await db.commit()
    await db.refresh(db_service, ["user"])

    return ServiceRead.model_validate(db_service, from_attributes=True)

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
        select(Service)
        .options(selectinload(Service.user))
        .where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this service"
        )

    update_data = service_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    await db.commit()
    result = await db.execute(
        select(Service)
        .options(selectinload(Service.user))
        .where(Service.id == service_id)
    )
    service = result.scalar_one()

    return ServiceRead.model_validate(service, from_attributes=True)

@router.put(
    "/{service_id}/with-image",
    response_model=ServiceRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid service data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this service"},
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def update_service_with_image(
    service_id: int,
    title: Optional[str] = Form(None, min_length=1, max_length=100),
    description: Optional[str] = Form(None, min_length=10, max_length=2000),
    is_offering: Optional[bool] = Form(None),
    is_active: Optional[bool] = Form(None),
    service_image: Optional[UploadFile] = File(None),
    meeting_locations: Optional[str] = Form(None),
    price_type: Optional[str] = Form(None),
    price_amount: Optional[float] = Form(None),
    estimated_duration_hours: Optional[float] = Form(None),
    contact_method: Optional[str] = Form(None),
    response_time_hours: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service)
        .options(selectinload(Service.user))
        .where(Service.id == service_id, Service.is_active == True)
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

    parsed_locations = service.meeting_locations
    if meeting_locations is not None:
        try:
            if meeting_locations.strip():
                parsed_locations = json.loads(meeting_locations)
                if not isinstance(parsed_locations, list):
                    raise ValueError("Invalid format")
                parsed_locations = [loc.strip() for loc in parsed_locations if loc.strip()][:5]
            else:
                parsed_locations = []
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid meeting_locations format. Must be JSON array of strings."
            )

    if price_type is not None and price_type not in ['free', 'paid', 'negotiable', 'exchange']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid price_type. Must be one of: free, paid, negotiable, exchange"
        )

    if contact_method is not None and contact_method not in ['message', 'phone', 'email']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid contact_method. Must be one of: message, phone, email"
        )

    if price_amount is not None and price_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price amount must be non-negative"
        )

    if estimated_duration_hours is not None and (estimated_duration_hours < 0.25 or estimated_duration_hours > 168):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estimated duration must be between 0.25 and 168 hours"
        )

    if response_time_hours is not None and (response_time_hours < 1 or response_time_hours > 168):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response time must be between 1 and 168 hours"
        )

    service_image_url = service.service_image_url
    if service_image:
        file_service = FileUploadService()
        try:
            if service.service_image_url:
                await file_service.delete_service_image(service.service_image_url)

            _, public_url = await file_service.upload_service_image(service_image, current_user.id)
            service_image_url = public_url
        except HTTPException:
            raise
        except Exception as e:
            print(f"Image upload error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload image"
            )

    if title is not None:
        service.title = title.strip()
    if description is not None:
        service.description = description.strip()
    if is_offering is not None:
        service.is_offering = is_offering
    if is_active is not None:
        service.is_active = is_active
    if meeting_locations is not None:
        service.meeting_locations = parsed_locations
    if price_type is not None:
        service.price_type = price_type
    if price_amount is not None:
        service.price_amount = price_amount
    if estimated_duration_hours is not None:
        service.estimated_duration_hours = estimated_duration_hours
    if contact_method is not None:
        service.contact_method = contact_method
    if response_time_hours is not None:
        service.response_time_hours = response_time_hours

    service.service_image_url = service_image_url

    service.updated_at = datetime.utcnow()

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Database error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update service"
        )

    return ServiceRead.model_validate(service, from_attributes=True)

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

@router.delete(
    "/{service_id}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this service"},
        404: {"model": ErrorResponse, "description": "Service not found"},
        400: {"model": ErrorResponse, "description": "Service has no image to delete"}
    }
)
async def delete_service_image(
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
            detail="Not authorized to edit this service"
        )

    if not service.service_image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service has no image to delete"
        )

    file_service = FileUploadService()
    try:
        await file_service.delete_service_image(service.service_image_url)
    except Exception as e:
        print(f"Warning: Failed to delete image file: {e}")
    service.service_image_url = None
    service.updated_at = datetime.utcnow()

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Database error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update service"
        )

    return None

@router.post(
    "/{service_id}/interest",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Cannot express interest in own service"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def express_interest(
    service_id: int,
    message: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot express interest in your own service"
        )

    service.interest_count += 1
    await db.commit()

    return {
        "message": "Interest expressed successfully",
        "new_interest_count": service.interest_count
    }

@router.post(
    "/{service_id}/interest/message",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Cannot express interest in own service"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def express_interest_with_message(
    service_id: int,
    message: str = Form(..., min_length=1, max_length=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot express interest in your own service"
        )

    return {
        "message": "Interest expressed and message sent",
        "conversation_created": True
    }

@router.get(
    "/my/stats",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_service_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).where(
            Service.user_id == current_user.id,
            Service.is_active == True
        )
    )
    user_services = result.scalars().all()

    total_services = len(user_services)
    offerings = len([s for s in user_services if s.is_offering])
    requests = len([s for s in user_services if not s.is_offering])

    return {
        "total_services": total_services,
        "active_offerings": offerings,
        "active_requests": requests,
        "total_interests_received": 0,  # TODO: Implement proper tracking
        "completion_rate": 0.0,
        "average_rating": 0.0,
        "response_time_hours": 0.0,
    }

@router.post(
    "/{service_id}/view",
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "Service not found"}
    }
)
async def increment_view_count(
    service_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if not current_user or service.user_id != current_user.id:
        service.view_count += 1
        await db.commit()

    return {"message": "View count incremented"}
