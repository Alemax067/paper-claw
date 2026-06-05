"""arxiv task subscriptions

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-05 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("arxiv_task_query_windows")
    op.drop_table("arxiv_task_paper_categories")
    op.drop_table("arxiv_task_categories")
    op.execute("delete from arxiv_task_harvest_jobs")
    op.execute("delete from arxiv_task_papers")
    op.alter_column("arxiv_task_harvest_jobs", "cat_ids_json", new_column_name="subscription_ids_json")

    op.create_table(
        "arxiv_task_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_subscriptions")),
        sa.UniqueConstraint("name", name=op.f("uq_arxiv_task_subscriptions_name")),
    )
    op.create_index(op.f("ix_arxiv_task_subscriptions_enabled"), "arxiv_task_subscriptions", ["enabled"], unique=False)

    op.create_table(
        "arxiv_task_paper_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("query_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["arxiv_task_papers.id"], name=op.f("fk_arxiv_task_paper_subscriptions_paper_id_arxiv_task_papers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["arxiv_task_subscriptions.id"], name=op.f("fk_arxiv_task_paper_subscriptions_subscription_id_arxiv_task_subscriptions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_paper_subscriptions")),
        sa.UniqueConstraint("paper_id", "subscription_id", name="uq_arxiv_task_paper_subscriptions_paper_subscription"),
    )
    op.create_index(op.f("ix_arxiv_task_paper_subscriptions_paper_id"), "arxiv_task_paper_subscriptions", ["paper_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_paper_subscriptions_subscription_id"), "arxiv_task_paper_subscriptions", ["subscription_id"], unique=False)

    op.create_table(
        "arxiv_task_query_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("query_snapshot", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_results", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warning_code", sa.String(length=120), nullable=True),
        sa.Column("parent_window_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["arxiv_task_harvest_jobs.id"], name=op.f("fk_arxiv_task_query_windows_job_id_arxiv_task_harvest_jobs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_window_id"], ["arxiv_task_query_windows.id"], name=op.f("fk_arxiv_task_query_windows_parent_window_id_arxiv_task_query_windows"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["arxiv_task_subscriptions.id"], name=op.f("fk_arxiv_task_query_windows_subscription_id_arxiv_task_subscriptions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_query_windows")),
    )
    op.create_index(op.f("ix_arxiv_task_query_windows_job_id"), "arxiv_task_query_windows", ["job_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_kind"), "arxiv_task_query_windows", ["kind"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_parent_window_id"), "arxiv_task_query_windows", ["parent_window_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_status"), "arxiv_task_query_windows", ["status"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_subscription_id"), "arxiv_task_query_windows", ["subscription_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_window_end"), "arxiv_task_query_windows", ["window_end"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_window_start"), "arxiv_task_query_windows", ["window_start"], unique=False)


def downgrade() -> None:
    op.drop_table("arxiv_task_query_windows")
    op.drop_table("arxiv_task_paper_subscriptions")
    op.drop_table("arxiv_task_subscriptions")
    op.execute("delete from arxiv_task_harvest_jobs")
    op.execute("delete from arxiv_task_papers")
    op.alter_column("arxiv_task_harvest_jobs", "subscription_ids_json", new_column_name="cat_ids_json")

    op.create_table(
        "arxiv_task_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cat_id", sa.String(length=40), nullable=False),
        sa.Column("top_area", sa.String(length=120), nullable=False),
        sa.Column("group", sa.String(length=120), nullable=True),
        sa.Column("group_code", sa.String(length=40), nullable=True),
        sa.Column("archive", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_alias", sa.Boolean(), nullable=False),
        sa.Column("alias_of", sa.String(length=40), nullable=True),
        sa.Column("api_exact_query", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_categories")),
        sa.UniqueConstraint("cat_id", name=op.f("uq_arxiv_task_categories_cat_id")),
    )
    op.create_index(op.f("ix_arxiv_task_categories_alias_of"), "arxiv_task_categories", ["alias_of"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_archive"), "arxiv_task_categories", ["archive"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_cat_id"), "arxiv_task_categories", ["cat_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_enabled"), "arxiv_task_categories", ["enabled"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_group"), "arxiv_task_categories", ["group"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_group_code"), "arxiv_task_categories", ["group_code"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_is_alias"), "arxiv_task_categories", ["is_alias"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_top_area"), "arxiv_task_categories", ["top_area"], unique=False)

    op.create_table(
        "arxiv_task_paper_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("cat_id", sa.String(length=40), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["arxiv_task_papers.id"], name=op.f("fk_arxiv_task_paper_categories_paper_id_arxiv_task_papers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_paper_categories")),
        sa.UniqueConstraint("paper_id", "cat_id", name="uq_arxiv_task_paper_categories_paper_cat"),
    )
    op.create_index(op.f("ix_arxiv_task_paper_categories_cat_id"), "arxiv_task_paper_categories", ["cat_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_paper_categories_paper_id"), "arxiv_task_paper_categories", ["paper_id"], unique=False)

    op.create_table(
        "arxiv_task_query_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cat_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_results", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warning_code", sa.String(length=120), nullable=True),
        sa.Column("parent_window_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["arxiv_task_harvest_jobs.id"], name=op.f("fk_arxiv_task_query_windows_job_id_arxiv_task_harvest_jobs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_window_id"], ["arxiv_task_query_windows.id"], name=op.f("fk_arxiv_task_query_windows_parent_window_id_arxiv_task_query_windows"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_query_windows")),
    )
    op.create_index(op.f("ix_arxiv_task_query_windows_cat_id"), "arxiv_task_query_windows", ["cat_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_job_id"), "arxiv_task_query_windows", ["job_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_kind"), "arxiv_task_query_windows", ["kind"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_parent_window_id"), "arxiv_task_query_windows", ["parent_window_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_status"), "arxiv_task_query_windows", ["status"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_window_end"), "arxiv_task_query_windows", ["window_end"], unique=False)
    op.create_index(op.f("ix_arxiv_task_query_windows_window_start"), "arxiv_task_query_windows", ["window_start"], unique=False)
