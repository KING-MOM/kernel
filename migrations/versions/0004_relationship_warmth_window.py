"""add relationship warmth_window_expires_at

Revision ID: 0004_relationship_warmth_window
Revises: 0003_outbox_intent_type
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_relationship_warmth_window"
down_revision = "0003_outbox_intent_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("relationships", sa.Column("warmth_window_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("relationships", "warmth_window_expires_at")
