"""Status constants and small helpers shared across services/views."""

STATUS_NEW = "New"
STATUS_DRAFTING = "Drafting"
STATUS_NEEDS_REVIEW = "Needs Review"
STATUS_NEEDS_REVISION = "Needs Revision"
STATUS_PUSHING = "Pushing"
STATUS_PUSHED = "Pushed"
STATUS_FAILED = "Failed"
STATUS_REJECTED = "Rejected"

ALL_STATUSES = [
    STATUS_NEW,
    STATUS_DRAFTING,
    STATUS_NEEDS_REVIEW,
    STATUS_NEEDS_REVISION,
    STATUS_PUSHING,
    STATUS_PUSHED,
    STATUS_FAILED,
    STATUS_REJECTED,
]

SOURCE_AI = "ai_generated"
SOURCE_MANUAL = "manual"

CAPTION_CHANNELS = ["facebook", "x", "linkedin", "instagram"]
