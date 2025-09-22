"""Add details_url column to product

Revision ID: c81b6d953c4b
Revises: b5dd427f5abd
Create Date: 2024-10-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c81b6d953c4b'
down_revision = 'b5dd427f5abd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('product', sa.Column('details_url', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('product', 'details_url')
