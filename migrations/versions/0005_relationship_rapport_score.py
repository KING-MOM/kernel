"""add relationship rapport_score

Revision ID: 0005_relationship_rapport_score
Revises: 0004_relationship_warmth_window
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_relationship_rapport_score"
down_revision = "0004_relationship_warmth_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("relationships", sa.Column("rapport_score", sa.Float(), nullable=True, server_default="0.0"))


def downgrade() -> None:
    op.drop_column("relationships", "rapport_score")
