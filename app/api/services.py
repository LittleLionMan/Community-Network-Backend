from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
import json

from app.database import get_db
from app.models.service import Service
from app.models.user import User
from app.models.business import ModerationAction
from app.schemas.service import (
    ServiceCreate, ServiceRead, ServiceUpdate, ServiceSummary
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_optional_current_user, get_current_admin_user
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

    return [ServiceSummary.model_validate(service) for service in services]

@router.get(
    "/admin",
    response_model=Dict[str, Any],
    summary="Get all services for admin management"
)
async def get_admin_services(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_offering: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_completed: Optional[bool] = Query(None),
    has_image: Optional[bool] = Query(None),
    flagged_only: bool = Query(False),
    sort_by: str = Query("created_at", regex="^(created_at|updated_at|view_count|interest_count|title)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Service).options(selectinload(Service.user))

    conditions = []

    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                Service.title.ilike(search_term),
                Service.description.ilike(search_term)
            )
        )

    if is_offering is not None:
        conditions.append(Service.is_offering == is_offering)

    if is_active is not None:
        conditions.append(Service.is_active == is_active)

    if is_completed is not None:
        conditions.append(Service.is_completed == is_completed)

    if has_image is not None:
        if has_image:
            conditions.append(Service.service_image_url.isnot(None))
        else:
            conditions.append(Service.service_image_url.is_(None))

    if flagged_only:
        # TODO: Join with moderation actions or flagged content
        pass

    if conditions:
        query = query.where(and_(*conditions))

    sort_column = getattr(Service, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    services = result.scalars().all()

    return {
        "services": [ServiceRead.model_validate(service) for service in services],
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size,
        "has_next": page * size < total,
        "has_prev": page > 1
    }

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

    stats = {
        "total_active_services": total_services,
        "services_offered": offerings,
        "services_requested": seekings,
        "market_balance": offerings / max(1, seekings) if seekings > 0 else float('inf')
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

    matching_service = ServiceMatchingService(db)
    recommendations = await matching_service.find_matching_services(
        user_id=current_user.id,
        limit=limit
    )

    return [ServiceSummary.model_validate(service) for service in recommendations]

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

    matching_service = ServiceMatchingService(db)
    potential_matches = await matching_service.find_matching_services(
        user_id=current_user.id,
        limit=3
    )

    service_response = ServiceRead.model_validate(db_service)

    if potential_matches:
        print(f"Found {len(potential_matches)} potential matches for user {current_user.id}")

    return service_response

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
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot express interest in your own service"
        )

    matching_service = ServiceMatchingService(db)
    success = await matching_service.create_service_request(
        user_id=current_user.id,
        service_id=service_id,
        message=message
    )

    if success:
        return {"message": "Interest expressed successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to express interest"
        )

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
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload image"
            )

    service_dict = {
        "title": title.strip(),
        "description": description.strip(),
        "is_offering": is_offering,
        "user_id": current_user.id,
        "service_image_url": service_image_url,
        "meeting_locations": parsed_locations[:5] if parsed_locations else None  # Limit to 5
    }

    db_service = Service(**service_dict)
    db.add(db_service)
    await db.commit()
    await db.refresh(db_service, ["user"])

    matching_service = ServiceMatchingService(db)
    potential_matches = await matching_service.find_matching_services(
        user_id=current_user.id,
        limit=3
    )

    if potential_matches:
        print(f"Found {len(potential_matches)} potential matches for user {current_user.id}")

    return ServiceRead.model_validate(db_service)

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

    if meeting_locations is not None:
        try:
            parsed_locations = json.loads(meeting_locations)
            if not isinstance(parsed_locations, list):
                raise ValueError("Invalid format")
            service.meeting_locations = parsed_locations[:5]
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid meeting_locations format. Must be JSON array."
            )

    if service_image:
        file_service = FileUploadService()
        try:
            if service.service_image_url:
                await file_service.delete_service_image(service.service_image_url)

            _, public_url = await file_service.upload_service_image(service_image, current_user.id)
            service.service_image_url = public_url
        except HTTPException:
            raise
        except Exception:
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

    await db.commit()
    await db.refresh(service, ["user"])

    return ServiceRead.model_validate(service)

@router.delete(
    "/{service_id}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this service"},
        404: {"model": ErrorResponse, "description": "Service not found"}
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

    if service.service_image_url:
        file_service = FileUploadService()
        await file_service.delete_service_image(service.service_image_url)
        service.service_image_url = None
        await db.commit()

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

    # Get interest counts (we'll need to implement this)
    total_interests_received = 0  # TODO: Count from ServiceInterest table

    return {
        "total_services": total_services,
        "active_offerings": offerings,
        "active_requests": requests,
        "total_interests_received": total_interests_received,
        "completion_rate": 0.0,
        "average_rating": 0.0,
        "response_time_hours": 0.0,
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
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if service.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot express interest in your own service"
        )

    matching_service = ServiceMatchingService(db)
    success = await matching_service.create_service_request(
        user_id=current_user.id,
        service_id=service_id,
        message=message
    )

    if success:
        return {
            "message": "Interest expressed and message sent",
            "conversation_created": True  # TODO: Return actual conversation ID
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to express interest"
        )

@router.get("/stats/detailed")
async def get_detailed_service_stats(
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

    services_with_images = len([s for s in services if s.service_image_url])

    services_with_locations = len([s for s in services if s.meeting_locations])

    stats = {
        "total_active_services": total_services,
        "services_offered": offerings,
        "services_requested": seekings,
        "market_balance": offerings / max(1, seekings) if seekings > 0 else float('inf'),
        "services_with_images_percent": (services_with_images / max(1, total_services)) * 100,
        "services_with_locations_percent": (services_with_locations / max(1, total_services)) * 100,
        "average_title_length": sum(len(s.title) for s in services) / max(1, total_services),
        "average_description_length": sum(len(s.description) for s in services) / max(1, total_services),
    }

    if current_user:
        user_services = [s for s in services if s.user_id == current_user.id]
        user_offerings = len([s for s in user_services if s.is_offering])
        user_requests = len([s for s in user_services if not s.is_offering])

        stats["user_stats"] = {
            "my_services": len(user_services),
            "my_offerings": user_offerings,
            "my_requests": user_requests,
            "my_services_with_images": len([s for s in user_services if s.service_image_url]),
            "my_services_with_locations": len([s for s in user_services if s.meeting_locations]),
        }

    return stats

@router.get(
    "/admin/stats",
    summary="Get service statistics for admin dashboard"
)
async def get_admin_service_stats(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    total_services_result = await db.execute(select(func.count(Service.id)))
    total_services = total_services_result.scalar() or 0

    active_services_result = await db.execute(
        select(func.count(Service.id)).where(Service.is_active == True)
    )
    active_services = active_services_result.scalar() or 0

    completed_services_result = await db.execute(
        select(func.count(Service.id)).where(Service.is_completed == True)
    )
    completed_services = completed_services_result.scalar() or 0

    offerings_result = await db.execute(
        select(func.count(Service.id)).where(
            and_(Service.is_active == True, Service.is_offering == True)
        )
    )
    active_offerings = offerings_result.scalar() or 0

    requests_result = await db.execute(
        select(func.count(Service.id)).where(
            and_(Service.is_active == True, Service.is_offering == False)
        )
    )
    active_requests = requests_result.scalar() or 0

    with_images_result = await db.execute(
        select(func.count(Service.id)).where(
            and_(Service.is_active == True, Service.service_image_url.isnot(None))
        )
    )
    with_images = with_images_result.scalar() or 0

    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_services_result = await db.execute(
        select(func.count(Service.id)).where(Service.created_at >= week_ago)
    )
    recent_services = recent_services_result.scalar() or 0

    top_viewed_result = await db.execute(
        select(Service).options(selectinload(Service.user))
        .where(Service.is_active == True)
        .order_by(desc(Service.view_count))
        .limit(5)
    )
    top_viewed = [ServiceSummary.model_validate(s) for s in top_viewed_result.scalars().all()]

    top_interest_result = await db.execute(
        select(Service).options(selectinload(Service.user))
        .where(Service.is_active == True)
        .order_by(desc(Service.interest_count))
        .limit(5)
    )
    top_interest = [ServiceSummary.model_validate(s) for s in top_interest_result.scalars().all()]

    return {
        "overview": {
            "total_services": total_services,
            "active_services": active_services,
            "completed_services": completed_services,
            "active_offerings": active_offerings,
            "active_requests": active_requests,
            "completion_rate": (completed_services / max(1, total_services)) * 100,
            "services_with_images": with_images,
            "image_usage_rate": (with_images / max(1, active_services)) * 100
        },
        "recent_activity": {
            "new_services_7d": recent_services,
            "growth_rate": (recent_services / max(1, total_services)) * 100
        },
        "top_performing": {
            "most_viewed": top_viewed,
            "most_interest": top_interest
        }
    }

@router.post(
    "/admin/{service_id}/moderate",
    summary="Moderate a service"
)
async def moderate_service(
    service_id: int,
    action: str,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    if action not in ['approve', 'flag', 'disable', 'enable']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be: approve, flag, disable, enable"
        )

    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    if action == 'disable':
        service.is_active = False
    elif action == 'enable':
        service.is_active = True
    moderation_action = ModerationAction(
        action_type=action,
        reason=reason,
        confidence_score=1.0,
        automated=False,
        moderator_id=current_user.id,
        content_type='service',
        content_id=service_id
    )
    db.add(moderation_action)

    await db.commit()

    return {
        "message": f"Service {action}d successfully",
        "service_id": service_id,
        "action": action,
        "moderator": current_user.display_name
    }

@router.post(
    "/admin/bulk-moderate",
    summary="Bulk moderate services"
)
async def bulk_moderate_services(
    service_ids: List[int],
    action: str,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    if action not in ['approve', 'flag', 'disable', 'enable', 'delete']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action"
        )

    if len(service_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot moderate more than 50 services at once"
        )

    result = await db.execute(
        select(Service).where(Service.id.in_(service_ids))
    )
    services = result.scalars().all()

    if len(services) != len(service_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Some services not found"
        )

    successful = 0
    failed = 0

    for service in services:
        try:
            if action == 'disable':
                service.is_active = False
            elif action == 'enable':
                service.is_active = True
            elif action == 'delete':
                service.is_active = False
            moderation_action = ModerationAction(
                action_type=action,
                reason=reason,
                confidence_score=1.0,
                automated=False,
                moderator_id=current_user.id,
                content_type='service',
                content_id=service.id
            )
            db.add(moderation_action)
            successful += 1

        except Exception as e:
            print(f"Failed to moderate service {service.id}: {e}")
            failed += 1

    await db.commit()

    return {
        "message": f"Bulk moderation completed",
        "successful": successful,
        "failed": failed,
        "action": action,
        "moderator": current_user.display_name
    }

@router.get(
    "/admin/{service_id}",
    response_model=ServiceRead,
    summary="Get service details for admin"
)
async def get_admin_service_detail(
    service_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Service).options(selectinload(Service.user))
        .where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    # Get moderation history
    moderation_result = await db.execute(
        select(ModerationAction)
        .where(
            and_(
                ModerationAction.content_type == 'service',
                ModerationAction.content_id == service_id
            )
        )
        .order_by(desc(ModerationAction.created_at))
        .limit(10)
    )
    moderation_history = moderation_result.scalars().all()

    service_data = ServiceRead.model_validate(service)

    return {
        **service_data.model_dump(),
        "admin_info": {
            "moderation_history": [
                {
                    "action": action.action_type,
                    "reason": action.reason,
                    "moderator_id": action.moderator_id,
                    "created_at": action.created_at,
                    "automated": action.automated
                } for action in moderation_history
            ]
        }
    }

@router.get(
    "/admin/user/{user_id}",
    summary="Get services by user for admin review"
)
async def get_user_services_admin(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    target_user = await db.get(User, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    result = await db.execute(
        select(Service).options(selectinload(Service.user))
        .where(Service.user_id == user_id)
        .order_by(desc(Service.created_at))
    )
    services = result.scalars().all()

    active_count = len([s for s in services if s.is_active])
    completed_count = len([s for s in services if s.is_completed])
    total_views = sum(s.view_count for s in services)
    total_interests = sum(s.interest_count for s in services)

    return {
        "user": {
            "id": target_user.id,
            "display_name": target_user.display_name,
            "email": target_user.email,
            "created_at": target_user.created_at,
            "is_active": target_user.is_active
        },
        "services": [ServiceRead.model_validate(service) for service in services],
        "stats": {
            "total_services": len(services),
            "active_services": active_count,
            "completed_services": completed_count,
            "total_views": total_views,
            "total_interests": total_interests,
            "average_views": total_views / max(1, len(services)),
            "completion_rate": (completed_count / max(1, len(services))) * 100
        }
    }
