"""upgrade memories for deepagents

Revision ID: f1e2d3c4b5a6
Revises: c9c1c108a5aa
Create Date: 2026-05-14 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f1e2d3c4b5a6"
down_revision = "c9c1c108a5aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_memories_type_name", "memories", type_="unique")
    op.add_column("memories", sa.Column("path", sa.String(length=1000), nullable=True))
    op.add_column("memories", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("memories", sa.Column("scope_type", sa.String(length=40), nullable=True))
    op.add_column("memories", sa.Column("scope_id", sa.String(length=255), nullable=True))
    op.add_column("memories", sa.Column("paper_id", sa.Integer(), nullable=True))
    op.add_column("memories", sa.Column("content_text", sa.Text(), nullable=True))
    op.add_column("memories", sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("memories", sa.Column("source", sa.String(length=40), nullable=True))
    op.add_column("memories", sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memories", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.execute(
        """
        UPDATE memories
        SET
            path = '/memories/legacy/' || memory_type || '/' || regexp_replace(lower(name), '[^a-z0-9._-]+', '-', 'g') || '.md',
            title = name,
            scope_type = 'global',
            paper_id = source_paper_id,
            content_text = content,
            source = 'agent',
            metadata_json = jsonb_build_object('legacy_name', name, 'legacy_description', description)
        """
    )
    op.alter_column("memories", "path", nullable=False)
    op.alter_column("memories", "scope_type", nullable=False)
    op.alter_column("memories", "content_text", nullable=False)
    op.alter_column("memories", "source", nullable=False)
    op.alter_column("memories", "metadata_json", nullable=False)
    op.create_unique_constraint("uq_memories_path", "memories", ["path"])
    op.create_index(op.f("ix_memories_memory_type"), "memories", ["memory_type"], unique=False)
    op.create_index(op.f("ix_memories_scope_id"), "memories", ["scope_id"], unique=False)
    op.create_index(op.f("ix_memories_scope_type"), "memories", ["scope_type"], unique=False)
    op.create_index(op.f("ix_memories_paper_id"), "memories", ["paper_id"], unique=False)
    op.create_index(op.f("ix_memories_source"), "memories", ["source"], unique=False)
    op.create_foreign_key(op.f("fk_memories_paper_id_papers"), "memories", "papers", ["paper_id"], ["id"], ondelete="SET NULL")
    op.drop_column("memories", "description")
    op.drop_column("memories", "content")
    op.drop_column("memories", "name")


def downgrade() -> None:
    op.add_column("memories", sa.Column("name", sa.String(length=160), nullable=True))
    op.add_column("memories", sa.Column("content", sa.Text(), nullable=True))
    op.add_column("memories", sa.Column("description", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE memories
        SET
            name = coalesce(title, path),
            content = content_text,
            description = metadata_json->>'legacy_description'
        """
    )
    op.alter_column("memories", "name", nullable=False)
    op.alter_column("memories", "content", nullable=False)
    op.drop_constraint(op.f("fk_memories_paper_id_papers"), "memories", type_="foreignkey")
    op.drop_index(op.f("ix_memories_source"), table_name="memories")
    op.drop_index(op.f("ix_memories_paper_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_scope_type"), table_name="memories")
    op.drop_index(op.f("ix_memories_scope_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_memory_type"), table_name="memories")
    op.drop_constraint("uq_memories_path", "memories", type_="unique")
    op.drop_column("memories", "metadata_json")
    op.drop_column("memories", "last_accessed_at")
    op.drop_column("memories", "source")
    op.drop_column("memories", "content_json")
    op.drop_column("memories", "content_text")
    op.drop_column("memories", "paper_id")
    op.drop_column("memories", "scope_id")
    op.drop_column("memories", "scope_type")
    op.drop_column("memories", "title")
    op.drop_column("memories", "path")
    op.create_unique_constraint("uq_memories_type_name", "memories", ["memory_type", "name"])
