"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-03-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agent_id", "external_id", name="uq_person_agent_external"),
    )
    op.create_index("ix_persons_agent_id", "persons", ["agent_id"])
    op.create_index("ix_persons_external_id", "persons", ["external_id"])

    op.create_table(
        "relationships",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("person_id", sa.String(), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("stage", sa.String(), nullable=False, server_default="onboarded"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("interaction_tension", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("intent_debt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_contact_at", sa.DateTime(), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(), nullable=True),
        sa.Column("debt_created_at", sa.DateTime(), nullable=True),
        sa.Column("dependency_blocked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("relationship_id", sa.String(), sa.ForeignKey("relationships.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "inbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("relationship_id", sa.String(), sa.ForeignKey("relationships.id"), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("sender_external_id", sa.String(), nullable=True),
        sa.Column("sender_email", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("body", sa.String(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("events.id"), nullable=True),
    )
    op.create_index("ix_inbox_message_id", "inbox", ["message_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_inbox_message_id", table_name="inbox")
    op.drop_table("inbox")
    op.drop_table("events")
    op.drop_table("relationships")
    op.drop_index("ix_persons_external_id", table_name="persons")
    op.drop_index("ix_persons_agent_id", table_name="persons")
    op.drop_table("persons")
