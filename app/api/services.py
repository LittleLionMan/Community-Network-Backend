from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
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

    return [ServiceSummary.model_validate(service) for service in services]

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

    # Handle image upload
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
    meeting_locations: Optional[str] = Form(None),  # JSON string
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

    # Update other fields
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
    """Express interest and create a conversation with the service provider"""

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

    # Create conversation and send message (integrate with message system)
    # This would use the existing message API to create a conversation

    # For now, we'll use the existing interest system
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

# Enhanced stats endpoint with more details
@router.get("/stats/detailed")
async def get_detailed_service_stats(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed platform service statistics"""

    # Basic platform stats
    result = await db.execute(
        select(Service).where(Service.is_active == True)
    )
    services = result.scalars().all()

    total_services = len(services)
    offerings = len([s for s in services if s.is_offering])
    seekings = len([s for s in services if not s.is_offering])

    # Services with images
    services_with_images = len([s for s in services if s.service_image_url])

    # Services with meeting locations
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
