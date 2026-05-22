"""add arxiv task harvester

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-05-22 00:00:00.000000
"""
from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("cs.AI", "Computer Science", "cs", "Artificial Intelligence", "Covers all areas of AI except vision, robotics, machine learning, multiagent systems, and computation and language."),
    ("cs.CL", "Computer Science", "cs", "Computation and Language", "Natural language processing, speech, and computational linguistics."),
    ("cs.CV", "Computer Science", "cs", "Computer Vision and Pattern Recognition", "Computer vision and pattern recognition."),
    ("cs.LG", "Computer Science", "cs", "Machine Learning", "Machine learning in computer science."),
    ("cs.IR", "Computer Science", "cs", "Information Retrieval", "Information retrieval, search, and recommender systems."),
    ("cs.DB", "Computer Science", "cs", "Databases", "Database systems and data management."),
    ("cs.SE", "Computer Science", "cs", "Software Engineering", "Software engineering methods and tools."),
    ("cs.RO", "Computer Science", "cs", "Robotics", "Robotics and autonomous systems."),
    ("cs.MA", "Computer Science", "cs", "Multiagent Systems", "Multiagent systems and distributed AI."),
    ("cs.NE", "Computer Science", "cs", "Neural and Evolutionary Computing", "Neural and evolutionary computing."),
    ("stat.ML", "Statistics", "stat", "Machine Learning", "Machine learning in statistics."),
    ("stat.AP", "Statistics", "stat", "Applications", "Applications of statistics."),
    ("stat.TH", "Statistics", "stat", "Statistics Theory", "Theoretical statistics."),
    ("eess.IV", "Electrical Engineering and Systems Science", "eess", "Image and Video Processing", "Image and video processing."),
    ("eess.AS", "Electrical Engineering and Systems Science", "eess", "Audio and Speech Processing", "Audio and speech processing."),
    ("eess.SP", "Electrical Engineering and Systems Science", "eess", "Signal Processing", "Signal processing."),
    ("math.OC", "Mathematics", "math", "Optimization and Control", "Optimization and control."),
    ("math.ST", "Mathematics", "math", "Statistics Theory", "Statistics theory."),
]


def upgrade() -> None:
    op.create_table(
        "arxiv_task_daily_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("run_time", sa.String(length=5), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_daily_config")),
    )
    op.create_index(op.f("ix_arxiv_task_daily_config_status"), "arxiv_task_daily_config", ["status"], unique=False)

    op.create_table(
        "arxiv_task_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cat_id", sa.String(length=40), nullable=False),
        sa.Column("group", sa.String(length=80), nullable=False),
        sa.Column("archive", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_categories")),
        sa.UniqueConstraint("cat_id", name=op.f("uq_arxiv_task_categories_cat_id")),
    )
    op.create_index(op.f("ix_arxiv_task_categories_archive"), "arxiv_task_categories", ["archive"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_cat_id"), "arxiv_task_categories", ["cat_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_enabled"), "arxiv_task_categories", ["enabled"], unique=False)
    op.create_index(op.f("ix_arxiv_task_categories_group"), "arxiv_task_categories", ["group"], unique=False)

    op.create_table(
        "arxiv_task_papers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("arxiv_id", sa.String(length=120), nullable=False),
        sa.Column("arxiv_base_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("authors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("primary_category", sa.String(length=40), nullable=True),
        sa.Column("categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("landing_page_url", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("journal_ref", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=500), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_papers")),
        sa.UniqueConstraint("arxiv_base_id", name=op.f("uq_arxiv_task_papers_arxiv_base_id")),
    )
    op.create_index(op.f("ix_arxiv_task_papers_arxiv_base_id"), "arxiv_task_papers", ["arxiv_base_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_papers_arxiv_id"), "arxiv_task_papers", ["arxiv_id"], unique=False)
    op.create_index(op.f("ix_arxiv_task_papers_doi"), "arxiv_task_papers", ["doi"], unique=False)
    op.create_index(op.f("ix_arxiv_task_papers_primary_category"), "arxiv_task_papers", ["primary_category"], unique=False)
    op.create_index(op.f("ix_arxiv_task_papers_published_at"), "arxiv_task_papers", ["published_at"], unique=False)
    op.create_index(op.f("ix_arxiv_task_papers_updated_at_source"), "arxiv_task_papers", ["updated_at_source"], unique=False)

    op.create_table(
        "arxiv_task_harvest_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("cat_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arxiv_task_harvest_jobs")),
    )
    op.create_index(op.f("ix_arxiv_task_harvest_jobs_kind"), "arxiv_task_harvest_jobs", ["kind"], unique=False)
    op.create_index(op.f("ix_arxiv_task_harvest_jobs_requested_end"), "arxiv_task_harvest_jobs", ["requested_end"], unique=False)
    op.create_index(op.f("ix_arxiv_task_harvest_jobs_requested_start"), "arxiv_task_harvest_jobs", ["requested_start"], unique=False)
    op.create_index(op.f("ix_arxiv_task_harvest_jobs_status"), "arxiv_task_harvest_jobs", ["status"], unique=False)

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

    now = datetime.now(UTC)
    op.bulk_insert(
        sa.table(
            "arxiv_task_daily_config",
            sa.column("status", sa.String),
            sa.column("run_time", sa.String),
            sa.column("metadata_json", postgresql.JSONB),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [{"status": "enabled", "run_time": "08:00", "metadata_json": {}, "created_at": now, "updated_at": now}],
    )
    op.bulk_insert(
        sa.table(
            "arxiv_task_categories",
            sa.column("cat_id", sa.String),
            sa.column("group", sa.String),
            sa.column("archive", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("enabled", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {"cat_id": cat_id, "group": group, "archive": archive, "name": name, "description": description, "enabled": False, "created_at": now, "updated_at": now}
            for cat_id, group, archive, name, description in CATEGORIES
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_arxiv_task_query_windows_window_start"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_window_end"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_status"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_parent_window_id"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_kind"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_job_id"), table_name="arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_query_windows_cat_id"), table_name="arxiv_task_query_windows")
    op.drop_table("arxiv_task_query_windows")
    op.drop_index(op.f("ix_arxiv_task_paper_categories_paper_id"), table_name="arxiv_task_paper_categories")
    op.drop_index(op.f("ix_arxiv_task_paper_categories_cat_id"), table_name="arxiv_task_paper_categories")
    op.drop_table("arxiv_task_paper_categories")
    op.drop_index(op.f("ix_arxiv_task_harvest_jobs_status"), table_name="arxiv_task_harvest_jobs")
    op.drop_index(op.f("ix_arxiv_task_harvest_jobs_requested_start"), table_name="arxiv_task_harvest_jobs")
    op.drop_index(op.f("ix_arxiv_task_harvest_jobs_requested_end"), table_name="arxiv_task_harvest_jobs")
    op.drop_index(op.f("ix_arxiv_task_harvest_jobs_kind"), table_name="arxiv_task_harvest_jobs")
    op.drop_table("arxiv_task_harvest_jobs")
    op.drop_index(op.f("ix_arxiv_task_papers_updated_at_source"), table_name="arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_papers_published_at"), table_name="arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_papers_primary_category"), table_name="arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_papers_doi"), table_name="arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_papers_arxiv_id"), table_name="arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_papers_arxiv_base_id"), table_name="arxiv_task_papers")
    op.drop_table("arxiv_task_papers")
    op.drop_index(op.f("ix_arxiv_task_categories_group"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_enabled"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_cat_id"), table_name="arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_categories_archive"), table_name="arxiv_task_categories")
    op.drop_table("arxiv_task_categories")
    op.drop_index(op.f("ix_arxiv_task_daily_config_status"), table_name="arxiv_task_daily_config")
    op.drop_table("arxiv_task_daily_config")
