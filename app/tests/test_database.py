import pytest
from app.models.user import User
from app.models.event import Event, EventCategory
from sqlalchemy import select
from datetime import datetime

class TestDatabaseModels:

    def test_create_user(self, db_session):
        user = User(
            display_name="testuser",
            email="test@example.com",
            password_hash="hashed_password"
        )

        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.display_name == "testuser"
        assert user.is_active is True  # Default value

    def test_user_event_relationship(self, db_session):
        # Create user
        user = User(
            display_name="eventcreator",
            email="creator@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create event category
        category = EventCategory(name="Test Category")
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)

        # Create event
        event = Event(
            title="Test Event",
            description="Test Description",
            start_datetime=datetime(2024, 12, 25, 18, 0,0),
            creator_id=user.id,
            category_id=category.id
        )
        db_session.add(event)
        db_session.commit()

        # Test relationship
        result = db_session.execute(
            select(User).where(User.id == user.id)
        )
        user_with_events = result.scalar_one()

        assert len(user_with_events.events) == 1
        assert user_with_events.events[0].title == "Test Event"
