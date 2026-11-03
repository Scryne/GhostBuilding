"""users.session_version — şifre sıfırlamada eski oturumları geçersiz kılmak için

Access ve refresh token'ları kullanıcının oturum sürümünü ``tv`` claim'i olarak taşır.
Şifre sıfırlama sürümü bir artırır; eski sürümü taşıyan token'lar reddedilir. Mevcut
satırlar 0 alır, ``tv`` taşımayan eski token'lar da 0 sayıldığı için kimse dışarı atılmaz.

Revision ID: a3
Revises: a2
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3"
down_revision: Union[str, None] = "a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
