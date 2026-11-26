import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.enums import (
    ActorType,
    ItemCategory,
    OrderStatus,
    RefundStatus,
    SenderType,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.models import (
    AuditEvent,
    Escalation,
    Message,
    Order,
    OrderItem,
    Refund,
    Ticket,
    TicketNote,
    User,
)


def seed_database(reset: bool = False, session: Session | None = None) -> None:
    owns_session = session is None
    if owns_session:
        session = SessionLocal()
    demo_password = os.getenv("SEED_PASSWORD", "LocalDevDemo123!")
    pw_hash = hash_password(demo_password)
    today = datetime.now(timezone.utc).date()

    try:
        if reset:
            print("Wiping existing data (--reset flag provided)...")
            # Clear tables in dependency order
            session.execute(delete(AuditEvent))
            session.execute(delete(Escalation))
            session.execute(delete(TicketNote))
            session.execute(delete(Message))
            session.execute(delete(Refund))
            session.execute(delete(Ticket))
            session.execute(delete(OrderItem))
            session.execute(delete(Order))
            session.execute(delete(User))
            session.commit()

        # 1. Seed Users (idempotent lookup by email)
        users_data = [
            ("Customer One", "customer1@example.com", UserRole.CUSTOMER),
            ("Customer Two", "customer2@example.com", UserRole.CUSTOMER),
            ("Support Agent Sarah", "agent1@example.com", UserRole.AGENT),
            ("System Admin Alex", "admin@example.com", UserRole.ADMIN),
        ]

        users_by_email: dict[str, User] = {}
        for name, email, role in users_data:
            existing = session.scalars(
                select(User).where(User.email == email.lower())
            ).first()
            if not existing:
                user = User(
                    name=name,
                    email=email.lower(),
                    password_hash=pw_hash,
                    role=role,
                )
                session.add(user)
                session.flush()
                users_by_email[email.lower()] = user
            else:
                users_by_email[email.lower()] = existing

        cust1 = users_by_email["customer1@example.com"]
        cust2 = users_by_email["customer2@example.com"]
        agent = users_by_email["agent1@example.com"]

        # 2. Seed Orders (Orders A through G)
        # Check if orders already seeded for cust1
        existing_orders = session.scalars(
            select(Order).where(Order.customer_id.in_([cust1.id, cust2.id]))
        ).all()

        orders_map: dict[str, Order] = {}

        if not existing_orders:
            # Order A: customer1, delivered 5 days ago, total 1,299, electronics -> eligible refund
            order_a = Order(
                order_number="ORD-1001",
                customer_id=cust1.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=5),
                total_amount=Decimal("1299.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=7),
            )
            order_a.items.append(
                OrderItem(
                    name="Wireless Bluetooth Earbuds",
                    category=ItemCategory.ELECTRONICS,
                    quantity=1,
                    unit_price=Decimal("1299.00"),
                )
            )
            session.add(order_a)

            # Order B: customer1, delivered 45 days ago, total 2,499, fashion -> return window expired
            order_b = Order(
                order_number="ORD-1002",
                customer_id=cust1.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=45),
                total_amount=Decimal("2499.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=50),
            )
            order_b.items.append(
                OrderItem(
                    name="Vintage Denim Jacket",
                    category=ItemCategory.FASHION,
                    quantity=1,
                    unit_price=Decimal("2499.00"),
                )
            )
            session.add(order_b)

            # Order C: customer1, delivered 3 days ago, total 8,999, electronics -> above 5,000, needs escalation
            order_c = Order(
                order_number="ORD-1003",
                customer_id=cust1.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=3),
                total_amount=Decimal("8999.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
            )
            order_c.items.append(
                OrderItem(
                    name="Mechanical Gaming Keyboard",
                    category=ItemCategory.ELECTRONICS,
                    quantity=1,
                    unit_price=Decimal("3999.00"),
                )
            )
            order_c.items.append(
                OrderItem(
                    name="Gaming Headset 7.1 Surround",
                    category=ItemCategory.ELECTRONICS,
                    quantity=1,
                    unit_price=Decimal("5000.00"),
                )
            )
            session.add(order_c)

            # Order D: customer1, shipped, not delivered yet, total 799 -> not refundable yet
            order_d = Order(
                order_number="ORD-1004",
                customer_id=cust1.id,
                status=OrderStatus.SHIPPED,
                delivery_date=None,
                total_amount=Decimal("799.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
            )
            order_d.items.append(
                OrderItem(
                    name="Insulated Stainless Water Bottle",
                    category=ItemCategory.HOME,
                    quantity=1,
                    unit_price=Decimal("799.00"),
                )
            )
            session.add(order_d)

            # Order E: customer1, delivered 10 days ago, with already PROCESSED refund -> duplicate/already refunded
            order_e = Order(
                order_number="ORD-1005",
                customer_id=cust1.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=10),
                total_amount=Decimal("1599.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=14),
            )
            order_e.items.append(
                OrderItem(
                    name="Performance Running Shoes",
                    category=ItemCategory.FASHION,
                    quantity=1,
                    unit_price=Decimal("1599.00"),
                )
            )
            session.add(order_e)
            session.flush()

            # Processed refund on Order E
            refund_e = Refund(
                order_id=order_e.id,
                amount=Decimal("1599.00"),
                reason="Wrong size delivered, returned and processed",
                status=RefundStatus.PROCESSED,
                requested_by=cust1.id,
                reviewed_by=agent.id,
                idempotency_key="idemp_order_e_processed_refund",
            )
            session.add(refund_e)

            # Order F: customer2, delivered 4 days ago, total 1,999 -> used for cross-customer access tests
            order_f = Order(
                order_number="ORD-1006",
                customer_id=cust2.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=4),
                total_amount=Decimal("1999.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=6),
            )
            order_f.items.append(
                OrderItem(
                    name="Smart Fitness Band",
                    category=ItemCategory.ELECTRONICS,
                    quantity=1,
                    unit_price=Decimal("1999.00"),
                )
            )
            session.add(order_f)

            # Order G: customer1, grocery, delivered 2 days ago, total 450 -> non-returnable category test
            order_g = Order(
                order_number="ORD-1007",
                customer_id=cust1.id,
                status=OrderStatus.DELIVERED,
                delivery_date=today - timedelta(days=2),
                total_amount=Decimal("450.00"),
                created_at=datetime.now(timezone.utc) - timedelta(days=3),
            )
            order_g.items.append(
                OrderItem(
                    name="Organic Green Tea Pack",
                    category=ItemCategory.GROCERY,
                    quantity=1,
                    unit_price=Decimal("450.00"),
                )
            )
            session.add(order_g)
            session.flush()

            orders_map["order_a"] = order_a
        else:
            orders_map["order_a"] = existing_orders[0]

        # 3. Seed sample Ticket with messages for customer1 on Order A
        existing_tickets = session.scalars(
            select(Ticket).where(Ticket.customer_id == cust1.id)
        ).first()

        if not existing_tickets:
            sample_ticket = Ticket(
                customer_id=cust1.id,
                order_id=orders_map["order_a"].id,
                subject="Defective earbuds received with order",
                description="Left earbud is not holding charge and fails to pair.",
                category=TicketCategory.ORDER_ISSUE,
                status=TicketStatus.OPEN,
                priority=TicketPriority.MEDIUM,
            )
            session.add(sample_ticket)
            session.flush()

            msg1 = Message(
                ticket_id=sample_ticket.id,
                sender_type=SenderType.CUSTOMER,
                sender_id=cust1.id,
                content="Hi, I received my wireless earbuds 5 days ago, but the left earbud doesn't charge. Can I get a replacement or refund?",
            )
            msg2 = Message(
                ticket_id=sample_ticket.id,
                sender_type=SenderType.SYSTEM,
                sender_id=None,
                content="Ticket #1001 created automatically. Support agent or AI assigned.",
            )
            msg3 = Message(
                ticket_id=sample_ticket.id,
                sender_type=SenderType.AGENT_AI,
                sender_id=None,
                content="Hello Customer! We apologize for the trouble with your earbuds. Since your order was delivered 5 days ago, you are within the 7-day return policy. Would you prefer a free replacement or a refund to your original payment method?",
            )
            session.add_all([msg1, msg2, msg3])

            # Audit event for ticket creation
            audit = AuditEvent(
                actor_id=cust1.id,
                actor_type=ActorType.CUSTOMER,
                event_type="ticket_created",
                entity_type="ticket",
                entity_id=sample_ticket.id,
                audit_metadata={"subject": sample_ticket.subject, "order_id": str(orders_map["order_a"].id)},
                request_id="seed_initial_request_id",
            )
            session.add(audit)

        session.commit()
        print("\n✅ Database seed completed successfully!")
        print("--------------------------------------------------")
        print("Demo Users Created:")
        print(f"  • Customer 1: customer1@example.com (Password: {demo_password})")
        print(f"  • Customer 2: customer2@example.com (Password: {demo_password})")
        print(f"  • Support Agent: agent1@example.com (Password: {demo_password})")
        print(f"  • Admin: admin@example.com (Password: {demo_password})")
        print("--------------------------------------------------")
        print("Orders Created:")
        print("  • Order A: delivered 5 days ago (1,299 INR, Electronics) - Eligible refund")
        print("  • Order B: delivered 45 days ago (2,499 INR, Fashion) - Window expired")
        print("  • Order C: delivered 3 days ago (8,999 INR, Electronics) - Escalation (>5,000)")
        print("  • Order D: shipped (799 INR, Home) - Not refundable yet")
        print("  • Order E: delivered 10 days ago (1,599 INR, Fashion) - Already PROCESSED refund")
        print("  • Order F: delivered 4 days ago (1,999 INR, Electronics) - Customer 2 order")
        print("  • Order G: delivered 2 days ago (450 INR, Grocery) - Non-returnable grocery")
        print("--------------------------------------------------\n")

    except Exception as exc:
        session.rollback()
        print(f"❌ Database seed failed: {exc}")
        raise
    finally:
        if owns_session:
            session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed initial database records.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe and recreate all records inside a transaction",
    )
    args = parser.parse_args()
    seed_database(reset=args.reset)


if __name__ == "__main__":
    main()
