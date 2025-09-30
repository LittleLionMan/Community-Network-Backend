from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from typing import Annotated

from app.database import get_db
from app.models.poll import Poll, PollOption, Vote
from app.models.forum import ForumThread
from app.models.user import User
from app.schemas.poll import (
    PollCreate,
    PollRead,
    PollUpdate,
    PollOptionRead,
    VoteCreate,
    VoteRead,
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_optional_current_user
from app.core.rate_limit_decorator import (
    poll_create_rate_limit,
    poll_vote_rate_limit,
    read_rate_limit,
)
from app.models.enums import PollType
from app.services.voting_service import VotingService

router = APIRouter()


@router.get(
    "/",
    response_model=list[PollRead],
    summary="Get all polls",
    description="Public endpoint to retrieve all active polls with pagination and filtering",
)
@read_rate_limit("general_api")
async def get_polls(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    poll_type: Annotated[
        PollType | None, Query(description="Filter by poll type")
    ] = None,
    active_only: Annotated[bool, Query(description="Show only active polls")] = True,
    thread_id: Annotated[int | None, Query(description="Filter by thread")] = None,
) -> list[PollRead]:
    query = select(Poll)

    if active_only:
        query = query.where(Poll.is_active)

    if poll_type:
        query = query.where(Poll.poll_type == poll_type)

    if thread_id:
        query = query.where(Poll.thread_id == thread_id)

    query = query.order_by(Poll.created_at.desc()).offset(skip).limit(limit)

    query = query.options(
        selectinload(Poll.creator),
        selectinload(Poll.thread),
        selectinload(Poll.options).selectinload(PollOption.votes),
    )

    result = await db.execute(query)
    polls = result.scalars().all()

    poll_results: list[PollRead] = []
    for poll in polls:
        poll_dict = PollRead.model_validate(poll, from_attributes=True).model_dump()

        total_votes = 0
        options_with_counts = []

        for option in poll.options:
            vote_count = len(option.votes)
            total_votes += vote_count

            option_dict = PollOptionRead.model_validate(
                option, from_attributes=True
            ).model_dump()
            option_dict["vote_count"] = vote_count
            options_with_counts.append(PollOptionRead.model_validate(option_dict))

        poll_dict["options"] = options_with_counts
        poll_dict["total_votes"] = total_votes

        poll_results.append(PollRead.model_validate(poll_dict))

    return poll_results


@router.get(
    "/{poll_id}",
    response_model=PollRead,
    responses={404: {"model": ErrorResponse, "description": "Poll not found"}},
)
async def get_poll(
    poll_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    include_analysis: Annotated[
        bool, Query(description="Include detailed vote analysis")
    ] = False,
):
    query = (
        select(Poll)
        .where(Poll.id == poll_id)
        .options(
            selectinload(Poll.creator),
            selectinload(Poll.thread),
            selectinload(Poll.options)
            .selectinload(PollOption.votes)
            .selectinload(Vote.user),
        )
    )

    result = await db.execute(query)
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found"
        )

    poll_dict = PollRead.model_validate(poll, from_attributes=True).model_dump()

    total_votes = 0
    options_with_counts = []
    user_vote = None

    for option in poll.options:
        vote_count = len(option.votes)
        total_votes += vote_count

        if current_user:
            for vote in option.votes:
                if vote.user_id == current_user.id:
                    user_vote = option.id
                    break

        option_dict = PollOptionRead.model_validate(
            option, from_attributes=True
        ).model_dump()
        option_dict["vote_count"] = vote_count
        options_with_counts.append(PollOptionRead.model_validate(option_dict))

    poll_dict["options"] = options_with_counts
    poll_dict["total_votes"] = total_votes

    if current_user and user_vote:
        poll_dict["user_vote"] = user_vote

    if include_analysis:
        voting_service = VotingService(db)
        analysis = await voting_service.analyze_poll_results(poll_id)
        poll_dict["analysis"] = analysis

    return PollRead.model_validate(poll_dict)


@router.post(
    "/",
    response_model=PollRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid poll data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to create this poll type",
        },
        404: {"model": ErrorResponse, "description": "Thread not found"},
    },
)
@poll_create_rate_limit
async def create_poll(
    poll_data: PollCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    auto_suggest_duration: Annotated[
        bool, Query(description="Auto-suggest optimal poll duration")
    ] = False,
):
    if poll_data.poll_type == PollType.ADMIN and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create admin polls",
        )

    if poll_data.thread_id:
        if poll_data.poll_type != PollType.THREAD:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="thread_id can only be specified for thread polls",
            )

        result = await db.execute(
            select(ForumThread).where(ForumThread.id == poll_data.thread_id)
        )
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
            )

        if thread.is_locked and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create poll in locked thread",
            )

    if poll_data.poll_type == PollType.ADMIN and poll_data.thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin polls cannot be attached to threads",
        )

    if len(poll_data.options) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Poll must have at least 2 options",
        )

    if len(poll_data.options) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Poll cannot have more than 10 options",
        )

    if auto_suggest_duration and not poll_data.ends_at:
        voting_service = VotingService(db)
        suggested_hours = await voting_service.suggest_poll_duration(
            poll_type=poll_data.poll_type.value, expected_participants=None
        )

        from datetime import datetime, timedelta

        poll_data.ends_at = datetime.now() + timedelta(hours=suggested_hours)

    poll_dict = poll_data.model_dump(exclude={"options"})
    poll_dict["creator_id"] = current_user.id

    db_poll = Poll(**poll_dict)
    db.add(db_poll)
    await db.commit()
    await db.refresh(db_poll)

    for option_data in poll_data.options:
        db_option = PollOption(
            poll_id=db_poll.id,
            text=option_data.text,
            order_index=option_data.order_index,
        )
        db.add(db_option)

    await db.commit()
    result = await db.execute(
        select(Poll)
        .where(Poll.id == db_poll.id)
        .options(
            selectinload(Poll.creator),
            selectinload(Poll.thread),
            selectinload(Poll.options),
        )
    )
    poll = result.scalar_one()

    poll_dict = PollRead.model_validate(poll, from_attributes=True).model_dump()
    poll_dict["total_votes"] = 0

    options_with_counts = []
    for option in poll.options:
        option_dict = PollOptionRead.model_validate(
            option, from_attributes=True
        ).model_dump()
        option_dict["vote_count"] = 0
        options_with_counts.append(PollOptionRead.model_validate(option_dict))

    poll_dict["options"] = options_with_counts

    return PollRead.model_validate(poll_dict)


@router.put(
    "/{poll_id}",
    response_model=PollRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid poll data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to edit this poll",
        },
        404: {"model": ErrorResponse, "description": "Poll not found"},
    },
)
async def update_poll(
    poll_id: int,
    poll_data: PollUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Poll)
        .where(Poll.id == poll_id)
        .options(selectinload(Poll.options).selectinload(PollOption.votes))
    )
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found"
        )

    if poll.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this poll",
        )

    has_votes = any(len(option.votes) > 0 for option in poll.options)

    if has_votes:
        allowed_changes = {"question", "ends_at", "is_active"}
        requested_changes = set(poll_data.model_dump(exclude_unset=True).keys())

        if not requested_changes.issubset(allowed_changes):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only change question, end date, or status once voting has started",
            )

    update_data: dict[str, object] = poll_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(poll, field, value)

    await db.commit()
    await db.refresh(poll, ["creator", "thread", "options"])

    return await get_poll(
        poll_id=poll_id, include_analysis=False, db=db, current_user=current_user
    )


@router.delete(
    "/{poll_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to delete this poll",
        },
        404: {"model": ErrorResponse, "description": "Poll not found"},
    },
)
async def delete_poll(
    poll_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Poll)
        .where(Poll.id == poll_id)
        .options(selectinload(Poll.options).selectinload(PollOption.votes))
    )
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found"
        )

    if poll.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this poll",
        )

    await db.delete(poll)
    await db.commit()


@router.post(
    "/{poll_id}/vote",
    response_model=VoteRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Poll ended, option not found, or already voted",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Poll not found"},
    },
)
@poll_vote_rate_limit
async def vote_on_poll(
    poll_id: int,
    vote_data: VoteCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Poll)
        .where(Poll.id == poll_id, Poll.is_active)
        .options(selectinload(Poll.options))
    )
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found or inactive"
        )

    if poll.ends_at:
        from datetime import datetime

        if poll.ends_at <= datetime.now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Poll has ended"
            )

    option_ids = [option.id for option in poll.options]
    if vote_data.option_id not in option_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid option for this poll",
        )

    result = await db.execute(
        select(Vote).where(Vote.poll_id == poll_id, Vote.user_id == current_user.id)
    )
    existing_vote = result.scalar_one_or_none()

    if existing_vote:
        existing_vote.option_id = vote_data.option_id
        await db.commit()
        await db.refresh(existing_vote, ["user", "option"])
        return VoteRead.model_validate(existing_vote, from_attributes=True)
    else:
        db_vote = Vote(
            poll_id=poll_id, user_id=current_user.id, option_id=vote_data.option_id
        )
        db.add(db_vote)
        await db.commit()
        await db.refresh(db_vote, ["user", "option"])
        return VoteRead.model_validate(db_vote, from_attributes=True)


@router.delete(
    "/{poll_id}/vote",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"model": ErrorResponse, "description": "No vote to remove"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Poll not found"},
    },
)
async def remove_vote(
    poll_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Poll).where(Poll.id == poll_id))
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found"
        )

    result = await db.execute(
        select(Vote).where(Vote.poll_id == poll_id, Vote.user_id == current_user.id)
    )
    vote = result.scalar_one_or_none()

    if not vote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No vote to remove"
        )

    _ = await db.execute(delete(Vote).where(Vote.id == vote.id))
    await db.commit()


@router.get(
    "/my/created",
    response_model=list[PollRead],
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def get_my_polls(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    result = await db.execute(
        select(Poll)
        .where(Poll.creator_id == current_user.id)
        .options(
            selectinload(Poll.creator),
            selectinload(Poll.thread),
            selectinload(Poll.options).selectinload(PollOption.votes),
        )
        .order_by(Poll.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    polls = result.scalars().all()

    poll_results: list[PollRead] = []
    for poll in polls:
        poll_dict = PollRead.model_validate(poll, from_attributes=True).model_dump()

        total_votes = 0
        options_with_counts = []

        for option in poll.options:
            vote_count = len(option.votes)
            total_votes += vote_count

            option_dict = PollOptionRead.model_validate(
                option, from_attributes=True
            ).model_dump()
            option_dict["vote_count"] = vote_count
            options_with_counts.append(PollOptionRead.model_validate(option_dict))

        poll_dict["options"] = options_with_counts
        poll_dict["total_votes"] = total_votes

        poll_results.append(PollRead.model_validate(poll_dict))

    return poll_results


@router.get(
    "/my/votes",
    response_model=list[VoteRead],
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def get_my_votes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    result = await db.execute(
        select(Vote)
        .where(Vote.user_id == current_user.id)
        .options(
            selectinload(Vote.user), selectinload(Vote.poll), selectinload(Vote.option)
        )
        .order_by(Vote.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    votes = result.scalars().all()

    return [VoteRead.model_validate(vote, from_attributes=True) for vote in votes]


@router.get(
    "/my/stats",
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def get_my_voting_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    voting_service = VotingService(db)
    stats = await voting_service.get_user_voting_stats(current_user.id)

    return stats


@router.get(
    "/{poll_id}/results",
    responses={404: {"model": ErrorResponse, "description": "Poll not found"}},
)
async def get_poll_results(
    poll_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    detailed: Annotated[bool, Query(description="Include detailed analysis")] = False,
):
    result = await db.execute(select(Poll).where(Poll.id == poll_id))
    poll = result.scalar_one_or_none()

    if not poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found"
        )

    voting_service = VotingService(db)
    results = await voting_service.analyze_poll_results(poll_id)

    if not detailed:
        return {
            "poll_id": results["poll_id"],
            "total_votes": results["total_votes"],
            "winners": results["winners"],
            "result_type": results["result_type"],
        }

    return results
