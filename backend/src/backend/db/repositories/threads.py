from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Message, Thread


class ThreadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, title: str, **values: object) -> Thread:
        thread = Thread(title=title, **values)
        self.session.add(thread)
        self.session.flush()
        return thread

    def get(self, thread_id: int) -> Thread | None:
        return self.session.get(Thread, thread_id)

    def list(self) -> list[Thread]:
        return list(self.session.scalars(select(Thread).order_by(Thread.updated_at.desc())))

    def add_message(self, thread_id: int, role: str, content_text: str | None = None, **values: object) -> Message:
        message = Message(thread_id=thread_id, role=role, content_text=content_text, created_at=datetime.now().astimezone(), **values)
        self.session.add(message)
        self.session.flush()
        return message
