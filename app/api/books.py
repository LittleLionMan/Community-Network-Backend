import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, get_optional_current_user
from app.core.rate_limit_decorator import read_rate_limit
from app.database import get_db
from app.models.book import Book
from app.models.book_offer import BookCondition, BookOffer
from app.models.user import User
from app.schemas.book import BookRead
from app.schemas.book_offer import (
    BookOfferCreate,
    BookOfferRead,
    BookOfferUpdate,
)
from app.services.book_service import BookService
from app.services.location_service import LocationService

router = APIRouter()


@router.get("/search")
@read_rate_limit("service_search")
async def search_book_by_isbn(
    isbn: Annotated[str, Query(min_length=10, max_length=13)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
):
    book_service = BookService(db)
    book = await book_service.search_or_create_book(isbn)

    if not book:
        raise HTTPException(
            status_code=404,
            detail="Buch-Metadaten konnten nicht gefunden werden. Bitte überprüfe die ISBN.",
        )

    return BookRead.model_validate(book)


@router.post("/offers", status_code=status.HTTP_201_CREATED)
async def create_offer(
    data: BookOfferCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.location_lat or not current_user.location_lon:
        if not data.custom_location:
            raise HTTPException(
                status_code=400,
                detail="Bitte hinterlege einen Standort in deinem Profil oder gib einen benutzerdefinierten Standort an.",
            )

    book_service = BookService(db)
    offer = await book_service.create_offer(current_user.id, data)

    return offer


@router.get("/offers/my")
async def get_my_offers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[
        str | None, Query(description="Filter: active, reserved, completed")
    ] = None,
):
    query = (
        select(BookOffer)
        .options(selectinload(BookOffer.book), selectinload(BookOffer.owner))
        .where(BookOffer.owner_id == current_user.id)
    )

    if status_filter == "active":
        query = query.where(BookOffer.is_available)
    elif status_filter == "reserved":
        query = query.where(
            BookOffer.reserved_by_user_id.isnot(None),
            BookOffer.is_available,
        )
    elif status_filter == "completed":
        query = query.where(BookOffer.is_available == False)

    query = query.order_by(BookOffer.created_at.desc())

    result = await db.execute(query)
    offers = result.scalars().all()

    book_service = BookService(db)
    offer_reads = []
    for offer in offers:
        all_comments = await book_service._get_all_user_comments(offer.book_id)
        offer_reads.append(BookOfferRead.from_db(offer, all_user_comments=all_comments))

    return offer_reads


@router.put("/offers/{offer_id}")
async def update_offer(
    offer_id: int,
    data: BookOfferUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    book_service = BookService(db)
    return await book_service.update_offer(offer_id, current_user.id, data)


@router.delete("/offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offer(
    offer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    book_service = BookService(db)
    _ = await book_service.delete_offer(offer_id, current_user.id)


@router.delete("/offers/{offer_id}/comment", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offer_comment(
    offer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = select(BookOffer).where(BookOffer.id == offer_id)
    result = await db.execute(query)
    offer = result.scalar_one_or_none()

    if not offer:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden")

    if offer.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Du kannst nur deine eigenen Kommentare löschen"
        )

    offer.user_comment = None
    await db.commit()


@router.get("/offers/{offer_id}")
@read_rate_limit("service_listing")
async def get_offer(
    offer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
):
    query = (
        select(BookOffer)
        .options(selectinload(BookOffer.book), selectinload(BookOffer.owner))
        .where(BookOffer.id == offer_id)
    )
    result = await db.execute(query)
    offer = result.scalar_one_or_none()

    if not offer:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden")

    distance_km = None
    if current_user and current_user.location_lat and current_user.location_lon:
        if offer.location_lat and offer.location_lon:
            distance_km = LocationService.calculate_distance_km(
                current_user.location_lat,
                current_user.location_lon,
                offer.location_lat,
                offer.location_lon,
            )

    book_service = BookService(db)
    all_comments = await book_service._get_all_user_comments(offer.book_id)

    return BookOfferRead.from_db(
        offer, distance_km=distance_km, all_user_comments=all_comments
    )


@router.get("/marketplace")
@read_rate_limit("service_listing")
async def get_marketplace(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    book_id: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    condition: Annotated[list[BookCondition] | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    max_distance_km: Annotated[float | None, Query(ge=1, le=100)] = None,
    district: Annotated[str | None, Query()] = None,
    has_comments: Annotated[bool | None, Query()] = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if search:
        search = search.strip()
        if len(search) < 2:
            search = None

    query = (
        select(BookOffer)
        .options(selectinload(BookOffer.book), selectinload(BookOffer.owner))
        .where(BookOffer.is_available)
    )

    if book_id:
        query = query.where(BookOffer.book_id == book_id)

    if current_user:
        query = query.where(BookOffer.owner_id != current_user.id)

    if condition:
        query = query.where(BookOffer.condition.in_(condition))

    if has_comments:
        query = query.where(
            BookOffer.user_comment.isnot(None), BookOffer.user_comment != ""
        )

    if search:
        query = query.join(Book).where(
            or_(
                Book.title.ilike(f"%{search}%"),
                Book.authors.astext.ilike(f"%{search}%"),
            )
        )

    if language:
        query = query.join(Book).where(Book.language == language)

    if category:
        query = query.join(Book).where(Book.categories.astext.ilike(f"%{category}%"))

    if district:
        query = query.where(BookOffer.location_district.ilike(f"%{district}%"))

    if max_distance_km and current_user:
        if current_user.location_lat and current_user.location_lon:
            lat_range = max_distance_km / 111.0
            cos_lat = math.cos(math.radians(current_user.location_lat))
            lon_range = max_distance_km / (111.0 * abs(cos_lat))

            query = query.where(
                and_(
                    BookOffer.location_lat.between(
                        current_user.location_lat - lat_range,
                        current_user.location_lat + lat_range,
                    ),
                    BookOffer.location_lon.between(
                        current_user.location_lon - lon_range,
                        current_user.location_lon + lon_range,
                    ),
                )
            )

    query = query.order_by(BookOffer.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    offers = result.scalars().all()

    offer_reads = []
    for offer in offers:
        distance_km = None
        if current_user and current_user.location_lat and current_user.location_lon:
            if offer.location_lat and offer.location_lon:
                distance_km = LocationService.calculate_distance_km(
                    current_user.location_lat,
                    current_user.location_lon,
                    offer.location_lat,
                    offer.location_lon,
                )

                if max_distance_km and distance_km > max_distance_km:
                    continue

        book_service = BookService(db)
        all_comments = await book_service._get_all_user_comments(offer.book_id)

        offer_reads.append(
            BookOfferRead.from_db(
                offer, distance_km=distance_km, all_user_comments=all_comments
            )
        )

    return offer_reads


@router.get("/stats")
@read_rate_limit("service_listing")
async def get_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
):
    total_books_query = select(func.count(Book.id.distinct()))
    total_offers_query = select(func.count(BookOffer.id))
    available_offers_query = select(func.count(BookOffer.id)).where(
        BookOffer.is_available
    )

    total_books = (await db.execute(total_books_query)).scalar() or 0
    total_offers = (await db.execute(total_offers_query)).scalar() or 0
    available_offers = (await db.execute(available_offers_query)).scalar() or 0

    stats = {
        "total_books": total_books,
        "total_offers": total_offers,
        "available_offers": available_offers,
    }

    if current_user:
        my_offers_query = select(func.count(BookOffer.id)).where(
            BookOffer.owner_id == current_user.id
        )
        my_available_query = select(func.count(BookOffer.id)).where(
            BookOffer.owner_id == current_user.id, BookOffer.is_available
        )

        stats["my_offers"] = (await db.execute(my_offers_query)).scalar() or 0
        stats["my_available"] = (await db.execute(my_available_query)).scalar() or 0

    return stats
