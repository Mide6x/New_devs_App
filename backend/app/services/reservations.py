from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any


def format_currency_amount(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    result = await calculate_total_revenue(property_id, tenant_id, month, year, db_session)
    return Decimal(result["total"])

async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: int | None = None,
    year: int | None = None,
    db_session=None,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    if month is not None and not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    if (month is None) != (year is None):
        raise ValueError("month and year must be supplied together")

    if db_session is None:
        await db_pool.initialize()
        session_context = db_pool.get_session()
    else:
        session_context = db_session

    query = text("""
            SELECT
                r.currency,
                COALESCE(SUM(r.total_amount), 0) AS total_revenue,
                COUNT(r.id) AS reservation_count
            FROM properties p
            LEFT JOIN reservations r
                ON r.property_id = p.id
                AND r.tenant_id = p.tenant_id
                AND (
                    :month IS NULL OR (
                        r.check_in_date >= (CAST(:period_start AS timestamp) AT TIME ZONE p.timezone)
                        AND r.check_in_date < (CAST(:period_end AS timestamp) AT TIME ZONE p.timezone)
                    )
                )
            WHERE p.id = :property_id AND p.tenant_id = :tenant_id
            GROUP BY r.currency
    """)
    params = {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "period_start": datetime(year, month, 1) if month else None,
        "period_end": datetime(year + (month == 12), 1 if month == 12 else month + 1, 1) if month else None,
    }

    if db_session is None:
        async with session_context as session:
            result = await session.execute(query, params)
            rows = result.fetchall()
    else:
        result = await session_context.execute(query, params)
        rows = result.fetchall()

    non_empty_rows = [row for row in rows if row.reservation_count]
    if len(non_empty_rows) > 1:
        raise ValueError("cannot combine revenue in multiple currencies")

    row = non_empty_rows[0] if non_empty_rows else None
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format_currency_amount(Decimal(str(row.total_revenue))) if row else "0.00",
        "currency": row.currency if row else "USD",
        "count": row.reservation_count if row else 0,
    }
