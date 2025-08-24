import pytest
from app.models.user import User
from app.models.event import Event, EventCategory
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models import Base
from datetime import datetime

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    session = SessionLocal()

    yield session

    session.rollback()
    session.close()
    Base.metadata.drop_all(bind=engine)

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
        assert user.is_active is True

    def test_user_event_relationship(self, db_session):
        user = User(
            display_name="eventcreator",
            email="creator@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        category = EventCategory(name="Test Category")
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)

        event = Event(
            title="Test Event",
            description="Test Description",
            start_datetime=datetime(2024, 12, 25, 18, 0, 0),
            creator_id=user.id,
            category_id=category.id
        )
        db_session.add(event)
        db_session.commit()

        result = db_session.execute(
            select(User).where(User.id == user.id)
        )
        user_with_events = result.scalar_one()

        assert len(user_with_events.events) == 1
        assert user_with_events.events[0].title == "Test Event"
