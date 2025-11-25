import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.service import Service, ServiceType
from app.models.user import User


async def create_book_exchange_service():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Service).where(Service.slug == "buecherecke"))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"✅ Service 'Bücherecke' existiert bereits (ID: {existing.id})")
            return existing.id

        admin_result = await db.execute(
            select(User).where(User.is_admin == True).limit(1)
        )
        admin_user = admin_result.scalar_one_or_none()

        if not admin_user:
            print("❌ FEHLER: Kein Admin-User gefunden!")
            print("💡 Lösung: Erstelle zuerst einen Admin-User")
            sys.exit(1)

        service = Service(
            slug="buecherecke",
            title="Bücherecke",
            description="Tausche Bücher mit anderen Community-Mitgliedern in deiner Nähe. Entdecke neue Geschichten und gib deinen gelesenen Büchern ein zweites Leben.",
            service_type=ServiceType.PLATFORM_FEATURE,
            user_id=admin_user.id,
            is_offering=True,
            is_active=True,
            contact_method="message",
        )

        db.add(service)
        await db.commit()
        await db.refresh(service)

        print("✅ Service 'Bücherecke' erfolgreich erstellt!")
        print(f"   - ID: {service.id}")
        print(f"   - Slug: {service.slug}")
        print(f"   - Type: {service.service_type.value}")
        print(f"   - Owner: {admin_user.display_name} (Admin)")
        print(f"   - URL: http://localhost:3000/services/buecherecke")
        print(f"\n🚀 Du kannst jetzt die Bücherecke nutzen!")

        return service.id


if __name__ == "__main__":
    asyncio.run(create_book_exchange_service())
