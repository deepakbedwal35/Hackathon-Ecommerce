from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SenderType, TicketCategory, TicketPriority, TicketStatus


class CustomerTicketListItem(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID | None = None
    subject: str
    category: TicketCategory
    status: TicketStatus
    priority: TicketPriority
    review_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerTicketDetail(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    order_id: uuid.UUID | None = None
    subject: str
    description: str
    category: TicketCategory
    status: TicketStatus
    priority: TicketPriority
    review_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerMessageRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID | None = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


class CustomerTicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    order_id: uuid.UUID | None = None
    category: TicketCategory = TicketCategory.OTHER

    model_config = ConfigDict(extra="forbid")


class CustomerTicketCreateResponse(BaseModel):
    ticket: CustomerTicketDetail
    agent_reply: CustomerMessageRead | None = None

    model_config = ConfigDict(from_attributes=True)


class CustomerMessagePostResponse(BaseModel):
    message: CustomerMessageRead
    agent_reply: CustomerMessageRead | None = None
    ticket_status: TicketStatus

    model_config = ConfigDict(from_attributes=True)
