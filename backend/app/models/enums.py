import enum


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class OrderStatus(str, enum.Enum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ItemCategory(str, enum.Enum):
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    GROCERY = "grocery"
    HOME = "home"
    BEAUTY = "beauty"
    BOOKS = "books"


class TicketCategory(str, enum.Enum):
    ORDER_ISSUE = "order_issue"
    REFUND = "refund"
    DELIVERY = "delivery"
    PAYMENT = "payment"
    PRODUCT = "product"
    OTHER = "other"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    AWAITING_CUSTOMER = "awaiting_customer"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class SenderType(str, enum.Enum):
    CUSTOMER = "customer"
    AGENT_AI = "agent_ai"
    STAFF = "staff"
    SYSTEM = "system"


class RefundStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


class EscalationDecision(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MORE_INFO_REQUESTED = "more_info_requested"


class ActorType(str, enum.Enum):
    CUSTOMER = "customer"
    STAFF = "staff"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"
