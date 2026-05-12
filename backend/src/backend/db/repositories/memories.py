from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Memory


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, memory_type: str, name: str, content: str, **values: object) -> Memory:
        memory = Memory(memory_type=memory_type, name=name, content=content, **values)
        self.session.add(memory)
        self.session.flush()
        return memory

    def get_by_name(self, memory_type: str, name: str) -> Memory | None:
        return self.session.scalar(select(Memory).where(Memory.memory_type == memory_type, Memory.name == name))
