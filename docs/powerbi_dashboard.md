# Rice Enterprise Power BI Dashboard

Connect Power BI to the Supabase PostgreSQL `postgres` database with DirectQuery. Use the Django table names `inventory_inventorybatch`, `inventory_delivery`, and `inventory_payment` unless the model table names are customized later.

## Measures

```DAX
Total Stock Volume =
SUM ( inventory_inventorybatch[qty_kg] )

Expired Stock Volume =
CALCULATE (
    [Total Stock Volume],
    FILTER (
        inventory_inventorybatch,
        inventory_inventorybatch[expiry_date] <= TODAY ()
    )
)

Pending Deliveries Count =
CALCULATE (
    COUNTROWS ( inventory_delivery ),
    inventory_delivery[delivery_status] <> "Delivered"
)

Next Delivery Date =
CALCULATE (
    MIN ( inventory_delivery[scheduled_date] ),
    inventory_delivery[delivery_status] <> "Delivered"
)

Paid Revenue =
CALCULATE (
    SUM ( inventory_payment[amount_due] ),
    inventory_payment[payment_status] = "Paid"
)

Unpaid Receivables =
CALCULATE (
    SUM ( inventory_payment[amount_due] ),
    inventory_payment[payment_status] = "Unpaid"
)
```

## Layout

1. Set the page canvas to `#EEF4F8` and use `#0B2545` for the header band.
2. Add four horizontal white KPI cards for `Total Stock Volume`, `Expired Stock Volume`, `Pending Deliveries Count`, and `Unpaid Receivables`. Use rounded corners and show `Expired Stock Volume` and `Unpaid Receivables` with alert-red accents (`#D90429`).
3. Add a bar chart with `inventory_inventorybatch[rice_type]` on the axis and `Total Stock Volume` as values. Set the series color to `#134074`.
4. Add a billing table using customer name from the related order, amount due, and payment status. Apply conditional formatting to payment status so `Unpaid` uses `#D90429` text.
5. Use `#8DA9C4` for secondary labels, dividers, and subdued chart elements. Add `Next Delivery Date` as a supporting card or tooltip value.

Ensure the model relationships are `inventory_order` to `inventory_delivery` and `inventory_payment` through their `order_id` foreign keys.

## Exact executive layout

Use a 16:9 page with a `#EEF4F8` canvas and a `#0B2545` header band. Use white (`#FFFFFF`) containers with a subtle shadow, 8-12 px corner radius, and consistent 16 px internal padding.

### Top KPI banner

Place four cards in one row on desktop and stack them in this order on mobile:

1. **Current Stock (kg)**: `Total Stock Volume`, navy value text (`#0B2545`).
2. **Expired / Critical Stock**: `Expired Stock Volume`, alert red (`#D90429`). Add a red risk label.
3. **Pending Deliveries**: `Pending Deliveries Count`, slate blue (`#134074`).
4. **Unpaid Collectibles**: `Unpaid Receivables`, alert red (`#D90429`).

### Middle visuals

- **Left, 60% width**: Clustered column chart. Axis: `inventory_inventorybatch[rice_type]`; values: `[Total Stock Volume]`; series color: `#134074`. Add a constant line at `10,000` on the Y axis, using `#D90429`, 2 px, dashed.
- **Right, 40% width**: Doughnut chart. Legend and values: `inventory_delivery[delivery_status]` and count of deliveries. Map `Delivered` to `#2A9D8F`, `In-Transit` to `#8DA9C4`, and `Pending` to `#0B2545`. Use a 65-70% inner radius.

### Bottom tables

- **Expiration Risk Matrix, 50% width**: Show batch `id`, `rice_type`, `qty_kg`, `expiry_date`, `days_until_expiry` (or a calculated Power BI column), and `stock_flag`. Apply red text/fill when days are less than or equal to 0 and yellow text/fill when days are 1-30.
- **Financial Receivables, 50% width**: Show `inventory_order[customer_name]`, order `id`, `inventory_payment[amount_due]`, related delivery `scheduled_date`, and `payment_status`. Use green pill styling for `Paid` and red pill styling for `Unpaid`.

## DirectQuery notes

- Refreshes query Supabase rather than importing a static snapshot.
- Keep the model relationships single-directional from `inventory_order` to deliveries and payments.
- Use the PostgreSQL Session Pooler connection from Supabase Connect when the workstation has no IPv6 database access.
- Validate that date fields are typed as Date/DateTime and that `qty_kg` and `amount_due` are Decimal/Fixed decimal.
- The Django dashboard's date filter is server-side; Power BI date slicers should filter the corresponding date dimensions or source date fields consistently.