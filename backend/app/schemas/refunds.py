from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import RefundStatus

PROGRESS_MAP: dict[RefundStatus, str] = {
    RefundStatus.PENDING_REVIEW: "Under Review",
    RefundStatus.APPROVED: "Approved",
    RefundStatus.PROCESSED: "Completed",
    RefundStatus.REJECTED: "Rejected",
    RefundStatus.FAILED: "Failed",
}


class RefundCreate(BaseModel):
    order_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    amount: Decimal
    reason: str = Field(min_length=10, max_length=1000)

    model_config = ConfigDict(extra="forbid")


class RefundRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    amount: Decimal
    reason: str
    status: RefundStatus
    payment_reference: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def progress(self) -> str:
        return PROGRESS_MAP.get(self.status, self.status.value.replace("_", " ").title())
