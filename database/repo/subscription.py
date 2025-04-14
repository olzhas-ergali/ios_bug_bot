from datetime import datetime, timedelta
from aiogram.types import Message
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Subscription
from database.repo.repo import Repo


class SubscriptionRepo(Repo):
    async def set_subscription(self, user_id: int, period: int) -> Subscription:
        async with self.sessionmaker() as session:
            async with session.begin():
                now_time = await self._get_subscription_end(user_id, session)
                end_time = (now_time or datetime.now()) + timedelta(days=period)

                subscription = await session.scalar(select(Subscription).where(Subscription.user_id == user_id))
                if subscription:
                    subscription.date_end = end_time
                    subscription.is_warn = False
                else:
                    subscription = Subscription(user_id=user_id, date_start=datetime.now(), date_end=end_time)
                    session.add(subscription)

                await session.commit()
                return subscription

    async def _get_subscription_end(self, user_id: int, session: AsyncSession) -> datetime | None:
        result = await session.scalar(select(Subscription.date_end).where(Subscription.user_id == user_id))
        return result

    async def get_expired(self):
        async with self.sessionmaker() as session:
            expired = await session.scalars(select(Subscription).where(Subscription.date_end <= datetime.now()))
            almost_expired = await session.scalars(
                select(Subscription).where(
                    (datetime.now() + timedelta(days=1) >= Subscription.date_end) & (Subscription.is_warn.is_(False))
                )
            )
            return expired.all(), almost_expired.all()

    async def delete_subscription(self, user_id: int):
        async with self.sessionmaker() as session:
            await session.execute(delete(Subscription).where(Subscription.user_id == user_id))
            await session.commit()

    async def warn_user(self, user_id: int):
        async with self.sessionmaker() as session:
            await session.execute(update(Subscription).where(Subscription.user_id == user_id).values(is_warn=True))
            await session.commit()
            
    async def check_crash_key_exists(self, crash_key: str) -> bool:
        async with self.sessionmaker() as session:
            result = await session.scalar(
                select(Subscription.id).where(Subscription.crash_key == crash_key).limit(1)
            )
        return result is not None

        
    async def save_crash_key(self, crash_key: str, user_id: int):
        async with self.sessionmaker() as session:
            session.add(Subscription(
                user_id=user_id,
                crash_key=crash_key,
                date_start=datetime.now()
            ))
            await session.commit()