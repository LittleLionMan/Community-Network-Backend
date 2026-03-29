from typing import TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def get_or_404(
    db: AsyncSession,
    query: Select[tuple[T]],
    detail: str = "Not found",
) -> T:
    result = await db.execute(query)
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )
    return entity


def apply_update(entity: object, schema: BaseModel) -> dict[str, object]:
    update_data: dict[str, object] = schema.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity, field, value)
    return update_data
