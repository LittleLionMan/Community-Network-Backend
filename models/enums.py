from enum import Enum

class ParticipationStatus(str, Enum):
    REGISTERED = "registered"
    ATTENDED = "attended"
    CANCELLED = "cancelled"

class PollType(str, Enum):
    THREAD = "thread"  # User-created polls in forum threads
    ADMIN = "admin"    # Admin-created polls for platform decisions
