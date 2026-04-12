"""Initial schema

Revision ID: a1
Revises: 
Create Date: 2026-04-12 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision: str = 'a1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Ensure PostGIS extension is created
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table('users',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('trust_score', sa.Float(), nullable=True),
    sa.Column('verified_count', sa.Integer(), nullable=True),
    sa.Column('submitted_count', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table('scan_jobs',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('center_lat', sa.Float(), nullable=False),
    sa.Column('center_lng', sa.Float(), nullable=False),
    sa.Column('radius_km', sa.Float(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('anomaly_count', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('anomalies',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lng', sa.Float(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_providers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('detection_methods', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('anomaly_images',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('anomaly_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('image_url', sa.String(), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('zoom_level', sa.Integer(), nullable=True),
    sa.Column('tile_x', sa.Integer(), nullable=True),
    sa.Column('tile_y', sa.Integer(), nullable=True),
    sa.Column('tile_z', sa.Integer(), nullable=True),
    sa.Column('diff_score', sa.Float(), nullable=True),
    sa.Column('is_blurred', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['anomaly_id'], ['anomalies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('verifications',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('anomaly_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('vote', sa.String(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['anomaly_id'], ['anomalies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('verifications')
    op.drop_table('anomaly_images')
    op.drop_table('anomalies')
    op.drop_table('scan_jobs')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
