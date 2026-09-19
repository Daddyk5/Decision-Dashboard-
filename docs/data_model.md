# Data Model and Business Rules

## InventoryBatch

Table: `inventory_inventorybatch`

| Field | Meaning |
|---|---|
| `id` | Django-generated batch identifier. |
| `rice_type` | Rice variety, such as Sinandomeng, Jasmine, Dinorado, or Sticky Rice. |
| `qty_kg` | Stock quantity in kilograms. Must be zero or greater. |
| `arrival_date` | Date the batch entered inventory. |
| `expiry_date` | Date after which the batch is expired. |

Computed values:

- `days_until_expiry` is `expiry_date - current local date`.
- `stock_flag` is `Expired` when days are less than or equal to zero, `Critical` when days are 1 through 30, and `Optimal` when days are greater than 30.
- The admin `stock flag` filter uses the same rules at query time.

## Order

Table: `inventory_order`

- `customer_name`: customer or account name.
- `order_date`: date placed; defaults to the current local date.
- `qty_ordered`: requested quantity in kilograms.
- `total_amount`: order value.

## Delivery

Table: `inventory_delivery`

- `order_id`: required foreign key to `inventory_order`; deleting an order deletes its deliveries.
- `scheduled_date`: planned delivery date.
- `delivery_status`: `Pending`, `In-Transit`, or `Delivered`.

Pending delivery metrics include both `Pending` and `In-Transit`; only `Delivered` is excluded.

## Payment

Table: `inventory_payment`

- `order_id`: required foreign key to `inventory_order`; deleting an order deletes its payments.
- `amount_due`: receivable amount; must be zero or greater.
- `payment_status`: `Paid` or `Unpaid`.

Outstanding receivables include only payments with status `Unpaid`.

## Operational relationships

```text
Order 1 ---- * Delivery
Order 1 ---- * Payment
```

Power BI should relate delivery and payment records to orders through `order_id`. Inventory batches are independent stock records and are grouped by `rice_type`.

## Customer

Table: `inventory_customer`. Customer profiles hold company/contact data, delivery address, and a non-negative credit limit. Orders created through the booking workflow reference `customer_id` and also snapshot `customer_name` for compatibility with historical records.

## Task

Table: `inventory_task`. Tasks are assigned to Django users and use `Low`, `Medium`, or `High` priority plus `To Do`, `In Progress`, or `Completed` status. Staff can update tasks assigned to themselves; managers with `change_task` can reassign or edit any task.

## StockAdjustment

Table: `inventory_stockadjustment`. Each adjustment records a signed `qty_kg`, reason, timestamp, request user, approval user, and approval state. The approval path locks the batch, rejects negative resulting stock, updates the batch quantity, and preserves the adjustment in the audit history.

The current enterprise fields are `qty_kg`, `requested_by`, `approved_by_tl`, and `is_approved`. Existing legacy audit columns are handled by migration `0004`; new requests remain pending until a Team Lead approves them.

## CallLog

Table: `inventory_calllog`. CSR agents record inbound/outbound customer calls, follow-up requirements, and optional TL escalation notes. The TL dashboard surfaces escalated calls; the CSR workstation surfaces the agent's follow-up queue.

Call compliance fields include `call_duration_seconds` and `terms_accepted`. Full call logging requires explicit consent; the floating quick logger records the same consent and duration fields.
