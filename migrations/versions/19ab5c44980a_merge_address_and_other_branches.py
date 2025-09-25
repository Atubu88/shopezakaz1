"""merge address and other branches

Revision ID: 19ab5c44980a
Revises: 48caf32d1d1d, 9fd0c18f4de2
Create Date: 2025-09-25 09:40:39.030344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19ab5c44980a'
down_revision: Union[str, Sequence[str], None] = ('48caf32d1d1d', '9fd0c18f4de2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
