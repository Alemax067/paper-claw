"""expand arxiv task categories

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 00:00:00.000000
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("arxiv_task_categories", sa.Column("top_area", sa.String(length=120), nullable=True))
    op.add_column("arxiv_task_categories", sa.Column("group_code", sa.String(length=40), nullable=True))
    op.add_column("arxiv_task_categories", sa.Column("is_alias", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("arxiv_task_categories", sa.Column("alias_of", sa.String(length=40), nullable=True))
    op.add_column("arxiv_task_categories", sa.Column("api_exact_query", sa.String(length=120), nullable=True))
    op.alter_column("arxiv_task_categories", "group", existing_type=sa.String(length=80), nullable=True, type_=sa.String(length=120))
    op.create_index(op.f("ix_arxiv_task_categories_top_area"), "arxiv_task_categories", ["top_area"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_group_code"), "arxiv_task_categories", ["group_code"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_is_alias"), "arxiv_task_categories", ["is_alias"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_alias_of"), "arxiv_task_categories", ["alias_of"], unique=False)

    _upsert_categories()

    op.alter_column("arxiv_task_categories", "top_area", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("arxiv_task_categories", "api_exact_query", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("arxiv_task_categories", "is_alias", server_default=None)


def downgrade() -> None:
    op.execute("update arxiv_task_categories set \"group\" = top_area where \"group\" is null")
    op.drop_index(op.f("ix_arxiv_task_categories_alias_of"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_is_alias"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_group_code"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_top_area"), table_name="arxiv_task_categories")
    op.alter_column("arxiv_task_categories", "group", existing_type=sa.String(length=120), nullable=False, type_=sa.String(length=80))
    op.drop_column("arxiv_task_categories", "api_exact_query")
    op.drop_column("arxiv_task_categories", "alias_of")
    op.drop_column("arxiv_task_categories", "is_alias")
    op.drop_column("arxiv_task_categories", "group_code")
    op.drop_column("arxiv_task_categories", "top_area")


def _upsert_categories() -> None:
    categories = _load_categories()
    now = datetime.now(UTC)
    connection = op.get_bind()
    table = sa.table(
        "arxiv_task_categories",
        sa.column("cat_id", sa.String),
        sa.column("top_area", sa.String),
        sa.column("group", sa.String),
        sa.column("group_code", sa.String),
        sa.column("archive", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_alias", sa.Boolean),
        sa.column("alias_of", sa.String),
        sa.column("api_exact_query", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_enabled = dict(connection.execute(sa.text("select cat_id, enabled from arxiv_task_categories")).all())
    for item in categories:
        cat_id = item["code"]
        values = {
            "cat_id": cat_id,
            "top_area": item["top_area"],
            "group": item.get("group"),
            "group_code": item.get("group_code"),
            "archive": item["archive"],
            "name": item["name"],
            "description": item.get("description"),
            "is_alias": bool(item.get("is_alias")),
            "alias_of": item.get("alias_of"),
            "api_exact_query": item["api_exact_query"],
            "enabled": bool(existing_enabled.get(cat_id, False)),
            "created_at": now,
            "updated_at": now,
        }
        if cat_id in existing_enabled:
            connection.execute(
                table.update().where(table.c.cat_id == cat_id).values(
                    top_area=values["top_area"],
                    group=values["group"],
                    group_code=values["group_code"],
                    archive=values["archive"],
                    name=values["name"],
                    description=values["description"],
                    is_alias=values["is_alias"],
                    alias_of=values["alias_of"],
                    api_exact_query=values["api_exact_query"],
                    updated_at=now,
                )
            )
        else:
            connection.execute(table.insert().values(**values))


def _load_categories() -> list[dict[str, object]]:
    path = Path(__file__).resolve().parents[2] / "src" / "backend" / "data" / "arxiv_categories_flat.json"
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise RuntimeError("arXiv category data must be a list")
    return data
