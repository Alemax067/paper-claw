from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.types import MemoryStatus, MemoryType

if TYPE_CHECKING:
    from backend.db.models.conversation import Thread
    from backend.db.models.papers import Paper


class Memory(TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (UniqueConstraint("memory_type", "name", name="uq_memories_type_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    memory_type: Mapped[str] = mapped_column(String(40), default=MemoryType.project.value, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_thread_id: Mapped[int | None] = mapped_column(ForeignKey("threads.id", ondelete="SET NULL"))
    source_paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), default=MemoryStatus.active.value, nullable=False, index=True)

    source_thread: Mapped[Thread | None] = relationship()
    source_paper: Mapped[Paper | None] = relationship()
