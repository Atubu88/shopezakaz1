"""add address and coordinates to order"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9fd0c18f4de2'
down_revision = 'c81b6d953c4b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('order', sa.Column('address', sa.String(length=255), nullable=True))
    op.add_column('order', sa.Column('lat', sa.Numeric(10, 6), nullable=True))
    op.add_column('order', sa.Column('lon', sa.Numeric(10, 6), nullable=True))


def downgrade() -> None:
    op.drop_column('order', 'lon')
    op.drop_column('order', 'lat')
    op.drop_column('order', 'address')
