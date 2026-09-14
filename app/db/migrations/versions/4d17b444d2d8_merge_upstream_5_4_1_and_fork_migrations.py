"""merge upstream 5.4.1 and fork migrations

Revision ID: 4d17b444d2d8
Revises: 48a6bcb8bba1, c4e8a91d5f37
Create Date: 2026-09-14 13:21:15.240362

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d17b444d2d8'
down_revision = ('48a6bcb8bba1', 'c4e8a91d5f37')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
