import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any, TypedDict, cast

import httpx

if TYPE_CHECKING:
    from app.models.user import User

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GeocodingResult(TypedDict):
    lat: float
    lon: float
    district: str


class LocationService:
    BASE_URL: str = "https://nominatim.openstreetmap.org/search"
    USER_AGENT: str = "CommunityPlatform/1.0"
    TIMEOUT: float = 10.0

    _lock: asyncio.Lock = asyncio.Lock()
    _last_request_time: float | None = None

    @classmethod
    async def _rate_limit(cls) -> None:
        async with cls._lock:
            if cls._last_request_time:
                elapsed = asyncio.get_event_loop().time() - cls._last_request_time
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
            cls._last_request_time = asyncio.get_event_loop().time()

    @classmethod
    async def geocode_location(cls, location_string: str) -> GeocodingResult | None:
        if not location_string or len(location_string.strip()) < 3:
            return None

        await cls._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                response = await client.get(
                    cls.BASE_URL,
                    params={
                        "q": location_string,
                        "format": "json",
                        "addressdetails": "1",
                        "limit": "1",
                    },
                    headers={"User-Agent": cls.USER_AGENT},
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Geocoding failed with status {response.status_code}"
                    )
                    return None

                data = cast(list[dict[str, Any]], response.json())
                if not data or len(data) == 0:
                    logger.info(f"No geocoding results for: {location_string}")
                    return None

                result: dict[str, Any] = data[0]
                lat = float(result.get("lat", 0))
                lon = float(result.get("lon", 0))

                address: dict[str, Any] = result.get("address", {})
                district = str(
                    address.get("suburb")
                    or address.get("district")
                    or address.get("neighbourhood")
                    or address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or "Unbekannt"
                )

                return GeocodingResult(lat=lat, lon=lon, district=district)

        except httpx.TimeoutException:
            logger.error(f"Geocoding timeout for: {location_string}")
            return None
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return None

    @staticmethod
    def round_coordinates(lat: float, lon: float) -> tuple[float, float]:
        return (round(lat, 2), round(lon, 2))

    @staticmethod
    def calculate_distance_km(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        R = 6371.0

        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c
        return round(distance, 2)

    @classmethod
    async def geocode_user_location(
        cls, db: AsyncSession, user: "User", location_string: str
    ) -> bool:
        result = await cls.geocode_location(location_string)
        if not result:
            return False

        lat_rounded, lon_rounded = cls.round_coordinates(result["lat"], result["lon"])

        user.location = location_string
        user.location_lat = lat_rounded
        user.location_lon = lon_rounded
        user.location_district = result["district"]
        user.location_geocoded_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(user)

        logger.info(
            f"Geocoded location for user {user.id}: {location_string} -> {result['district']}"
        )
        return True
