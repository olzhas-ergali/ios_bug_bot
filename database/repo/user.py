from aiogram.types import Message
from sqlalchemy import select

from database.models import User
from database.repo.repo import Repo


class UserRepo(Repo):
    async def find_user_by_user_id(self, user_id) -> User:
        async with self.sessionmaker() as session:
            query = (
                select(User)
                .filter_by(user_id=user_id)
            )
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            return user

    async def save_user(self, message: Message) -> User:
        async with self.sessionmaker() as session:
            user = self.create_user_from_contact(message)
            async with session.begin():
                session.add(user)
                await session.commit()

            result = await session.execute(
                select(User).filter_by(user_id=user.user_id)
            )
            user = result.scalar_one_or_none()
            return user

    @staticmethod
    def create_user_from_contact(message: Message) -> User:
        user = User()
        contact = message.contact
        user.username = message.from_user.username
        user.fullname = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        user.user_id = contact.user_id
        user.phone_number = contact.phone_number
        return user

    async def upsert_user(self, user_id: int = None, **user_data):
        async with self.sessionmaker() as session:
            if user_id is not None:
                async with session.begin():
                    result = await session.execute(select(User).filter_by(user_id=user_id))
                    user = result.scalar_one_or_none()
                    if user:
                        for key, value in user_data.items():
                            setattr(user, key, value)
                    else:
                        user = User(**user_data)
                        session.add(user)
            else:
                user = User(**user_data)
                session.add(user)
            await session.commit()
            return user
