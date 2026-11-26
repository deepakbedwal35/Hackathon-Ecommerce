# Database Schema Documentation

This document describes the database architecture, table relationships, and key business invariants for Part 2 of the E-Commerce AI Customer Support platform.

---

## Entity-Relationship Diagram

```mermaid
erDiagram
    users ||--o{ orders : "places"
    users ||--o{ tickets : "creates"
    users ||--o{ messages : "sends"
    users ||--o{ refunds : "requests/reviews"
    users ||--o{ ticket_notes : "authors"
    users ||--o{ escalations : "assigned_to"
    users ||--o{ audit_events : "actor"

    orders ||--|{ order_items : "contains"
    orders ||--o{ refunds : "has"
    orders ||--o{ tickets : "referenced_by"

    tickets ||--|{ messages : "contains"
    tickets ||--o{ ticket_notes : "has"
    tickets ||--o{ escalations : "triggers"
    tickets ||--o{ refunds : "associated_with"

    refunds ||--o{ escalations : "escalated_via"

    users {
        uuid id PK
        varchar name
        varchar email UK "lower() indexed"
        varchar password_hash
        user_role role "customer, agent, admin"
        timestamptz created_at
    }

    orders {
        uuid id PK
        uuid customer_id FK "RESTRICT"
        order_status status "placed, shipped, delivered, cancelled"
        date delivery_date "nullable"
        numeric total_amount "CHECK >= 0"
        timestamptz created_at
    }

    order_items {
        uuid id PK
        uuid order_id FK "CASCADE"
        varchar name
        item_category category "electronics, fashion, grocery, home, beauty, books"
        int quantity "CHECK > 0"
        numeric unit_price "CHECK >= 0"
    }

    tickets {
        uuid id PK
        uuid customer_id FK "RESTRICT"
        uuid order_id FK "SET NULL"
        varchar subject
        text description
        ticket_category category "order_issue, refund, delivery, payment, product, other"
        ticket_status status "open, awaiting_customer, escalated, resolved, closed"
        ticket_priority priority "low, medium, high, urgent"
        timestamptz created_at
        timestamptz updated_at
    }

    messages {
        uuid id PK
        uuid ticket_id FK "CASCADE"
        sender_type sender_type "customer, agent_ai, staff, system"
        uuid sender_id FK "SET NULL"
        text content
        timestamptz created_at
    }

    refunds {
        uuid id PK
        uuid order_id FK "RESTRICT"
        uuid ticket_id FK "SET NULL"
        numeric amount "CHECK > 0"
        text reason
        refund_status status "pending_review, approved, rejected, processed, failed"
        uuid requested_by FK "RESTRICT"
        uuid reviewed_by FK "RESTRICT"
        varchar idempotency_key UK
        text failure_reason
        timestamptz created_at
        timestamptz updated_at
    }

    escalations {
        uuid id PK
        uuid ticket_id FK "RESTRICT"
        uuid refund_id FK "RESTRICT"
        text summary
        ticket_priority priority "low, medium, high, urgent"
        uuid assigned_to FK "RESTRICT"
        escalation_decision decision "pending, approved, rejected, more_info_requested"
        text internal_note
        timestamptz created_at
        timestamptz decided_at
    }

    ticket_notes {
        uuid id PK
        uuid ticket_id FK "CASCADE"
        uuid author_id FK "RESTRICT"
        text note
        timestamptz created_at
    }

    audit_events {
        uuid id PK
        uuid actor_id FK "SET NULL"
        actor_type actor_type "customer, staff, ai_agent, system"
        varchar event_type
        varchar entity_type
        uuid entity_id
        jsonb metadata "default {}"
        varchar request_id
        timestamptz created_at
    }
```

---

## Key Invariants

1. **One Active Refund Per Order**:
   - Enforced by PostgreSQL partial unique index:
     ```sql
     CREATE UNIQUE INDEX uq_refunds_one_active_per_order
     ON refunds (order_id)
     WHERE status IN ('pending_review', 'approved', 'processed');
     ```
   - Terminal statuses (`rejected`, `failed`) free the slot, permitting a customer to file a subsequent eligible claim.

2. **Strict Financial Type Safety (No Float)**:
   - All monetary fields (`orders.total_amount`, `order_items.unit_price`, `refunds.amount`) use `Numeric(12, 2)`.
   - Single currency (INR) without fractional sub-paisa float rounding hazards.
   - Enforced by positive check constraints (`total_amount >= 0`, `unit_price >= 0`, `amount > 0`).

3. **Refund Idempotency**:
   - Every refund record requires a unique, non-null `idempotency_key` (`uq_refunds_idempotency_key`).
   - Prevents duplicate payouts from network retries, concurrent agent actions, or double submissions.

4. **Deliberate Referential Integrity (ON DELETE RESTRICT)**:
   - Financial ledger records (`orders`, `refunds`, `users`) cannot be deleted if referenced (`ON DELETE RESTRICT`).
   - `ON DELETE CASCADE` is permitted strictly on parent-dependent sub-entities (`order_items` on order delete, `messages` and `ticket_notes` on ticket delete).

5. **Append-Only Audit Log**:
   - `audit_events` is an immutable, append-only log capturing user, staff, system, and AI agent actions. Records are never updated or deleted.
