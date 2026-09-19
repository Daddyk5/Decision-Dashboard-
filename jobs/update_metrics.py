#!/usr/bin/env python
"""Refresh and report inventory metrics from the Supabase PostgreSQL database."""

import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def build_database_url():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    return URL.create(
        'postgresql+psycopg2',
        username=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME', 'postgres'),
    )


def update_metrics():
    engine = create_engine(
        build_database_url(),
        connect_args={'sslmode': os.getenv('DB_SSLMODE', 'require')},
        pool_pre_ping=True,
    )
    try:
        batches = pd.read_sql_query(
            text(
                """
                SELECT rice_type, qty_kg, arrival_date, expiry_date,
                       CASE
                           WHEN expiry_date <= CURRENT_DATE THEN 'Expired'
                           WHEN expiry_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'Critical'
                           ELSE 'Optimal'
                       END AS stock_flag
                FROM inventory_inventorybatch
                """
            ),
            engine,
        )
        unpaid = pd.read_sql_query(
            text(
                """
                SELECT COALESCE(SUM(amount_due), 0) AS total_outstanding
                FROM inventory_payment
                WHERE payment_status = 'Unpaid'
                """
            ),
            engine,
        )
    finally:
        engine.dispose()

    healthy_stock = batches.loc[batches['stock_flag'].isin(['Critical', 'Optimal']), 'qty_kg'].sum()
    expired_stock = batches.loc[batches['stock_flag'] == 'Expired', 'qty_kg'].sum()
    outstanding = unpaid.iloc[0]['total_outstanding']
    logger.info('Metrics update complete: healthy stock=%s kg, expired stock=%s kg, unpaid balances=%s', healthy_stock, expired_stock, outstanding)
    return {'healthy_stock_kg': healthy_stock, 'expired_stock_kg': expired_stock, 'unpaid_balances': outstanding}


if __name__ == '__main__':
    update_metrics()