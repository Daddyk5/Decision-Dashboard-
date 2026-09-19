#!/usr/bin/env python
"""Generate safe demo activity for the Rice Enterprise dashboard."""

import argparse
import os
import random
import sys
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
from django.db import transaction
from django.utils import timezone

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / '.env')
django.setup()

from inventory.models import Delivery, InventoryBatch, Order, Payment  # noqa: E402


CUSTOMERS = ('Lotus Foods', 'Maharaja Grocers', 'Harvest Table', 'Golden Grain Co.')
RICE_TYPES = ('Sinandomeng', 'Jasmine', 'Dinorado', 'Sticky Rice')


def run_cycle():
    with transaction.atomic():
        batch = InventoryBatch.objects.select_for_update().order_by('-qty_kg').first()
        if batch is None:
            batch = InventoryBatch.objects.create(
                rice_type=random.choice(RICE_TYPES),
                qty_kg=Decimal('25000'),
                arrival_date=timezone.localdate(),
                expiry_date=timezone.localdate() + timedelta(days=90),
            )

        quantity = min(Decimal(random.randint(250, 1250)), batch.qty_kg)
        batch.qty_kg = batch.qty_kg - quantity
        batch.save(update_fields=('qty_kg',))

        order = Order.objects.create(
            customer_name=random.choice(CUSTOMERS),
            order_date=timezone.localdate(),
            qty_ordered=quantity,
            total_amount=quantity * Decimal(random.choice(('1.85', '2.10', '2.40'))),
        )
        delivery = Delivery.objects.create(
            order=order,
            scheduled_date=timezone.localdate() + timedelta(days=random.randint(1, 5)),
            delivery_status=Delivery.Status.PENDING,
        )
        payment = Payment.objects.create(
            order=order,
            amount_due=order.total_amount,
            payment_status=Payment.Status.UNPAID,
        )

    print(
        f'Created order #{order.pk}: {quantity} kg from batch #{batch.pk}; '
        f'delivery #{delivery.pk}; payment #{payment.pk}; remaining stock={batch.qty_kg} kg',
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=int, default=10, help='Seconds between demo cycles.')
    parser.add_argument('--once', action='store_true', help='Run one cycle and exit.')
    args = parser.parse_args()

    if args.once:
        run_cycle()
        return

    print(f'Simulator running every {args.interval} seconds. Press CTRL+C to stop.', flush=True)
    while True:
        run_cycle()
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
