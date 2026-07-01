"""SQLAlchemy async ORM matching db/schema.sql."""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mneme.config import settings


class Base(DeclarativeBase):
    """Shared declarative base."""


class CoreBlock(Base):
    """Structured large-grained user model block.

    Letta read-only primary pattern:
      - sleep_agent: SOLE writer
      - awake_agent: READ ONLY (enforced in memory.store)
    """

    __tablename__ = "core_blocks"

    label: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_writer: Mapped[str] = mapped_column(
        Text, nullable=False, default="sleep_agent"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArchivalFact(Base):
    """Small-grained user fact + vector embedding."""

    __tablename__ = "archival_facts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    source: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MemoryOpsLog(Base):
    """Append-only audit log of every memory mutation."""

    __tablename__ = "memory_ops_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    op_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# -------------------------------------------------------------
# Engine + session factory (lazy singletons).
# -------------------------------------------------------------

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=10,
            max_overflow=5,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def dispose_engine() -> None:
    """Close the engine. Call from app shutdown lifespan."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
