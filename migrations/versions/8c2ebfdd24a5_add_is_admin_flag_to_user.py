"""add is_admin flag to user

Revision ID: 8c2ebfdd24a5
Revises: 559b3246316b
Create Date: 2024-09-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c2ebfdd24a5'
down_revision: Union[str, Sequence[str], None] = '559b3246316b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.alter_column('user', 'is_admin', server_default=None)


def downgrade() -> None:
    op.drop_column('user', 'is_admin')
