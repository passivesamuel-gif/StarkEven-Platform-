from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .engine.notifications import schedule_low_credit_check
from .errors import InsufficientCredits
from .models import Organization


async def spend_credits(db: AsyncSession, org_id: int, amount: int) -> int:
    """Atomically deduct credits; raises InsufficientCredits if the balance is too low.
    Returns the new balance. Commits."""
    res = await db.execute(
        update(Organization)
        .where(Organization.id == org_id, Organization.credit_balance >= amount)
        .values(credit_balance=Organization.credit_balance - amount)
        .returning(Organization.credit_balance)
        .execution_options(synchronize_session=False)
    )
    new_balance = res.scalar_one_or_none()
    if new_balance is None:
        await db.rollback()
        raise InsufficientCredits()
    await db.commit()
    schedule_low_credit_check(org_id, int(new_balance))
    return new_balance


async def spend_org_credits(org_id: int, amount: int = 1) -> int:
    """Same, on its own short-lived session (used by the bulk worker)."""
    from . import db as dbmod

    async with dbmod.SessionLocal() as s:
        return await spend_credits(s, org_id, amount)
