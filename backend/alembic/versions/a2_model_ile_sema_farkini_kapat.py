"""Model ile şema farkını kapat

İlk migration (a1) modellerin gerisinde kalmıştı: temiz bir kurulumda ``users`` tablosunda
parola, etkinlik ve doğrulama sütunları yoktu, bu yüzden kayıt ve giriş 500 veriyordu.
Testler SQLite üzerinde tabloları modelden kurduğu için fark hiç görünmedi.

Revision ID: a2
Revises: a1
Create Date: 2026-09-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2"
down_revision: Union[str, None] = "a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("hashed_password", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    op.add_column("scan_jobs", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "scan_jobs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_foreign_key(
        "fk_scan_jobs_user_id_users", "scan_jobs", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )

    op.create_index(
        "ix_anomalies_category_status_confidence",
        "anomalies",
        ["category", "status", "confidence_score"],
    )
    op.create_index(
        "ix_anomalies_covering",
        "anomalies",
        ["category", "status", "lat", "lng", "confidence_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_anomalies_covering", table_name="anomalies")
    op.drop_index("ix_anomalies_category_status_confidence", table_name="anomalies")
    op.drop_constraint("fk_scan_jobs_user_id_users", "scan_jobs", type_="foreignkey")
    op.drop_column("scan_jobs", "created_at")
    op.drop_column("scan_jobs", "user_id")
    op.drop_column("users", "created_at")
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_active")
    op.drop_column("users", "hashed_password")
