from aiogram.types import Message
from sqlalchemy import select

from database.models import User
from database.repo.repo import Repo
from typing import List, Optional


class UserRepo(Repo):
    
    async def find_all(self) -> list[User]:
        async with self.sessionmaker() as session:
            query = select(User)
            result = await session.scalars(query)
            return result.all() or []

    async def find_user_by_user_id(self, user_id) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(user_id=user_id)
            return await session.scalar(query) or User()

    async def find_user_by_username(self, username) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(username=username)
            return await session.scalar(query) or User()

    async def save_user(self, message: Message) -> User:
        async with self.sessionmaker() as session:
            existing_user = await session.execute(
                select(User).filter_by(user_id=message.from_user.id)
            )
            existing_user = existing_user.scalar_one_or_none()

            if existing_user:
                return existing_user

            new_user = self.create_user_from_contact(message)
            session.add(new_user)
            await session.commit()

            return new_user
        
    async def get_users_by_language(self, lang: str) -> List[User]:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(lang=lang)
            result = await session.scalars(query)
            return result.all() if result else [] 

    @staticmethod
    def create_user_from_contact(message: Message) -> User:
        user = User()
        contact = message.contact
        user.username = message.from_user.username
        # user.fullname = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        user.user_id = message.from_user.id
        user.phone_number = contact.phone_number
        return user

    async def upsert_user(self, user_id: int = None, **user_data):
        async with self.sessionmaker() as session:
            if user_id is not None:
                async with session.begin():
                    result = await session.execute(
                        select(User).filter_by(user_id=user_id))
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
        

    async def get_admins(self) -> list[User]:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(role='admin')
            result = await session.scalars(query)
            return result.all() or []
        
    async def get_or_create_user(self, user_id: int, username: Optional[str] = None) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(user_id=user_id)
            user = await session.scalar(query)
            if not user:
                user = User(user_id=user_id, username=username)
                session.add(user)
                await session.commit()
            return user