"""
Refund and return policy rules, thresholds, and time helpers.
"""
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.enums import ItemCategory

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


def get_today_date() -> date:
    """Returns today's date in the Asia/Kolkata timezone."""
    return datetime.now(KOLKATA_TZ).date()


ClockCallable = Callable[[], date]

# Return window in days measured from order.delivery_date
RETURN_WINDOW_DAYS: int = int(settings.RETURN_WINDOW_DAYS)

# Maximum refund amount eligible for instant automated processing (5000.00 INR)
# Any amount strictly greater than this requires human review and escalation.
AUTO_REFUND_LIMIT: Decimal = Decimal(str(settings.AUTO_REFUND_LIMIT))

# Non-returnable merchandise categories
# Design choice: An order containing ANY item in this set is treated as non-returnable
# to prevent partial returns of perishable/hygiene goods under e-commerce standard terms.
NON_RETURNABLE_CATEGORIES: set[ItemCategory] = {
    ItemCategory(cat) for cat in settings.NON_RETURNABLE_CATEGORIES if cat in ItemCategory._value2member_map_
} or {ItemCategory.GROCERY}
