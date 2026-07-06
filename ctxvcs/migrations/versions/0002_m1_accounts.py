"""M1 self-serve accounts (§ Core 14): password_hash + display_name on members.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("members", "display_name")
    op.drop_column("members", "password_hash")
