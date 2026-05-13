from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from backend.db.session import get_session

SessionFactory = Callable[[], Session]

_session_factory: SessionFactory | None = None


def set_tool_session_factory(factory: SessionFactory | None) -> None:
    global _session_factory
    _session_factory = factory


@contextmanager
def tool_session() -> Iterator[Session]:
    if _session_factory is not None:
        session = _session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return
    with get_session() as session:
        yield session
