from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ItemCategory, OrderStatus
from app.schemas.refunds import RefundRead


class CustomerOrderItemRead(BaseModel):
    id: uuid.UUID
    name: str
    category: ItemCategory
    quantity: int
    unit_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class CustomerOrderListItem(BaseModel):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    total_amount: Decimal
    delivery_date: date | None = None
    created_at: datetime
    item_count: int
    refund_status: str | None = None
    is_returnable: bool = False

    model_config = ConfigDict(from_attributes=True)


class CustomerOrderDetail(BaseModel):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    total_amount: Decimal
    delivery_date: date | None = None
    created_at: datetime
    items: list[CustomerOrderItemRead]
    refunds: list[RefundRead]
    is_returnable: bool = False
    last_eligible_date: date | None = None
    refundable_amount: Decimal

    model_config = ConfigDict(from_attributes=True)
