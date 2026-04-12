import enum

class AnomalyCategory(str, enum.Enum):
    GHOST_BUILDING = "GHOST_BUILDING"
    HIDDEN_STRUCTURE = "HIDDEN_STRUCTURE"
    CENSORED_AREA = "CENSORED_AREA"
    IMAGE_DISCREPANCY = "IMAGE_DISCREPANCY"

class AnomalyStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    UNDER_REVIEW = "UNDER_REVIEW"

class ImageProvider(str, enum.Enum):
    OSM = "OSM"
    GOOGLE = "GOOGLE"
    BING = "BING"
    YANDEX = "YANDEX"
    SENTINEL = "SENTINEL"
    WAYBACK = "WAYBACK"

class VerificationVote(str, enum.Enum):
    CONFIRM = "CONFIRM"
    DENY = "DENY"
    UNCERTAIN = "UNCERTAIN"

class UserRole(str, enum.Enum):
    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"

class ScanJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
