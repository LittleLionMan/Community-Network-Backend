from datetime import datetime, timezone
from typing import Sequence


def serialize_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")


def serialize_datetime_list(dates: Sequence[datetime | str]) -> list[str]:
    result = []
    for d in dates:
        if isinstance(d, datetime):
            result.append(serialize_datetime(d))
        elif isinstance(d, str):
            if d.endswith("+00:00"):
                result.append(d.replace("+00:00", "Z"))
            elif not d.endswith("Z") and "T" in d:
                try:
                    dt = datetime.fromisoformat(d)
                    result.append(serialize_datetime(dt))
                except (ValueError, AttributeError):
                    result.append(d)
            else:
                result.append(d)
        else:
            result.append(str(d))
    return result
