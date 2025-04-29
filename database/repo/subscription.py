from datetime import datetime, timedelta
from aiogram.types import Message
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database.models import Subscription
from database.repo.repo import Repo


class SubscriptionRepo(Repo):
    async def get_subscription(self, user_id: int, crash_key: str) -> Optional[Subscription]:
        """Получает запись подписки по user_id и crash_key."""
        async with self.sessionmaker() as session:
            result = await session.scalar(
                select(Subscription)
                .where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.crash_key == crash_key
                    )
                )
            )
            return result

    async def create_or_reset_subscription(
        self,
        user_id: int,
        crash_key: str,
        start_date: datetime,
        end_date: datetime
    ) -> bool:
        """Создает новую подписку или сбрасывает счетчик и даты существующей.
           Используется при первом платном анализе для crash_key.
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Попытка найти существующую подписку по crash_key (он уникален)
                existing_sub = await session.scalar(
                    select(Subscription).where(Subscription.crash_key == crash_key)
                )

                if existing_sub:
                    # Если нашли, проверяем пользователя и обновляем/сбрасываем
                    if existing_sub.user_id == user_id:
                        existing_sub.analysis_count = 1 # Сбрасываем счетчик до 1 (т.к. 1 анализ уже прошел)
                        existing_sub.date_start = start_date
                        existing_sub.date_end = end_date
                        existing_sub.is_warn = False # Сбрасываем флаг предупреждения
                        await session.commit()
                        return True
                    else:
                         # Ключ существует, но у другого пользователя - ошибка (не должно происходить из-за unique constraint)
                         await session.rollback()
                         return False
                else:
                    # Если не нашли, создаем новую
                    new_sub = Subscription(
                        user_id=user_id,
                        crash_key=crash_key,
                        analysis_count=1, # Начинаем с 1
                        date_start=start_date,
                        date_end=end_date,
                        is_warn=False
                    )
                    session.add(new_sub)
                    await session.commit()
                    return True
        return False # На случай непредвиденной ошибки

    async def increment_analysis_count(self, user_id: int, crash_key: str) -> bool:
        """Увеличивает счетчик бесплатных анализов для активной подписки."""
        async with self.sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    update(Subscription)
                    .where(
                        and_(
                            Subscription.user_id == user_id,
                            Subscription.crash_key == crash_key,
                            Subscription.date_end > func.now(), # Убедимся, что подписка активна
                            Subscription.analysis_count < 10 # Убедимся, что лимит не достигнут
                        )
                    )
                    .values(analysis_count=Subscription.analysis_count + 1)
                    .returning(Subscription.id)
                )
                updated_id = result.scalar_one_or_none()
                if updated_id:
                await session.commit()
                    return True
                else:
                    # Не удалось обновить (подписка не найдена, истекла или лимит исчерпан)
                    await session.rollback()
                    return False

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