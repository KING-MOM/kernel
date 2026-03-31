"""add outbox intent_type and rapport_eligible

Revision ID: 0003_outbox_intent_type
Revises: 0002_outbox_outcome_payload
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_outbox_intent_type"
down_revision = "0002_outbox_outcome_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox", sa.Column("intent_type", sa.String(), nullable=True))
    op.add_column("outbox", sa.Column("rapport_eligible", sa.Boolean(), nullable=True, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("outbox", "rapport_eligible")
    op.drop_column("outbox", "intent_type")
