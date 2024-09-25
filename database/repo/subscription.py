from datetime import datetime, timedelta

from aiogram.types import Message
from sqlalchemy import select, update, delete

from database.models import Subscription
from database.repo.repo import Repo


class SubscriptionRepo(Repo):
    async def set_subscription(self, user_id, period):
        sub = Subscription()

        now_time = await self._renew_subscription(user_id)
        end_time = (datetime.now() if now_time is None else now_time) + timedelta(days=period)
        # end_time = (datetime.now() if now_time is None else now_time) + timedelta(days=period)

        async with self.sessionmaker() as session:
            sub.user_id = user_id
            sub.date_start = (datetime.now() if now_time is None else now_time)
            sub.date_end = end_time

            if now_time is None:
                session.add(sub)
                await session.commit()
            else:
                stmt = update(Subscription).where(Subscription.user_id==sub.user_id).values(date_end=sub.date_end)
                await session.execute(stmt)
                await session.commit()
            return sub

    async def _renew_subscription(self, user_id):
        async with self.sessionmaker() as session:
            query = select(Subscription).where(Subscription.user_id == user_id)
            result = await session.scalar(query)
        return None if result is None else result.date_end

    async def get_expired(self):
        async with self.sessionmaker() as session:
            query = select(Subscription).where(Subscription.date_end <= datetime.now())
            expired = await session.scalars(query)

            query = select(Subscription).where((datetime.now() - timedelta(1) <= Subscription.date_end) & Subscription.is_warn.is_(False))
            almost_expired = await session.scalars(query)

            return (expired.all(), almost_expired.all()) or ([],[])

    async def delete(self, user_id):
        async with self.sessionmaker() as session:
            query = delete(Subscription).where(Subscription.user_id == user_id)

            await session.execute(query)
            await session.commit()

    async def warn(self, user_id):
        async with self.sessionmaker() as session:
            query = update(Subscription).where(Subscription.user_id == user_id).values(is_warn=True)

            await session.execute(query)
            await session.commit()
