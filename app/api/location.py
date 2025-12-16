from fastapi import APIRouter
from pydantic import BaseModel

from app.services.location_service import LocationService

router = APIRouter()


class LocationValidationRequest(BaseModel):
    location: str


class LocationValidationResponse(BaseModel):
    valid: bool
    district: str | None = None
    lat: float | None = None
    lon: float | None = None
    formatted_address: str | None = None
    message: str


@router.post("/validate", response_model=LocationValidationResponse)
async def validate_location(data: LocationValidationRequest):
    if not data.location or len(data.location.strip()) < 3:
        return LocationValidationResponse(
            valid=False, message="Standort muss mindestens 3 Zeichen haben"
        )

    result = await LocationService.geocode_location(data.location)

    if not result:
        return LocationValidationResponse(
            valid=False,
            message="Standort konnte nicht gefunden werden. Bitte überprüfe die Schreibweise.",
        )

    lat_rounded, lon_rounded = LocationService.round_coordinates(
        result["lat"], result["lon"]
    )

    return LocationValidationResponse(
        valid=True,
        district=result["district"],
        lat=lat_rounded,
        lon=lon_rounded,
        formatted_address=result["formatted_address"],
        message=f"Standort gefunden: {result['district']}",
    )
