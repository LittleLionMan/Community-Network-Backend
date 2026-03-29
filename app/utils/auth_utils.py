from fastapi import HTTPException, status

from app.models.user import User


def check_ownership(
    entity: object,
    current_user: User,
    *,
    owner_field: str = "creator_id",
    action: str = "modify",
    entity_name: str = "resource",
) -> None:
    owner_id = getattr(entity, owner_field)
    if owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to {action} this {entity_name}",
        )
