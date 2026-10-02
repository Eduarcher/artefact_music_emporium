import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporium.db.models import Customer, Message, Session


def new_session_id() -> str:
    return uuid.uuid4().hex


async def customer_exists(
    session_factory: async_sessionmaker[AsyncSession], customer_id: int
) -> bool:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Customer.customer_id).where(Customer.customer_id == customer_id)
            )
        ).scalar_one_or_none()
    return row is not None


async def create_session(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    customer_id: int,
    model: str,
    prompt_version: str,
) -> Session:
    session_row = Session(
        session_id=new_session_id(),
        customer_id=customer_id,
        model=model,
        prompt_version=prompt_version,
    )
    async with session_factory() as session:
        session.add(session_row)
        await session.commit()
    return session_row


async def get_session(
    session_factory: async_sessionmaker[AsyncSession], session_id: str
) -> Session | None:
    async with session_factory() as session:
        return (
            await session.execute(select(Session).where(Session.session_id == session_id))
        ).scalar_one_or_none()


async def get_customer_name(
    session_factory: async_sessionmaker[AsyncSession], customer_id: int
) -> str | None:
    async with session_factory() as session:
        return (
            await session.execute(
                select(Customer.name).where(Customer.customer_id == customer_id)
            )
        ).scalar_one_or_none()


async def get_transcript(
    session_factory: async_sessionmaker[AsyncSession], session_id: str
) -> list[BaseMessage]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.id)
            )
        ).scalars().all()

    messages: list[BaseMessage] = []
    for row in rows:
        if row.role == "user":
            messages.append(HumanMessage(content=row.content))
        elif row.role == "assistant":
            messages.append(AIMessage(content=row.content))
    return messages


async def add_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    session_id: str,
    role: str,
    content: str,
) -> Message:
    message = Message(session_id=session_id, role=role, content=content)
    async with session_factory() as session:
        session.add(message)
        await session.commit()
    return message
