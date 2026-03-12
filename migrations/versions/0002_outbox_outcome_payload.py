"""add outbox outcome payload

Revision ID: 0002_outbox_outcome_payload
Revises: 0001_initial
Create Date: 2026-03-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0002_outbox_outcome_payload"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox", sa.Column("outcome_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("outbox", "outcome_payload")
