"""sensor_readings

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FEATURE_COLUMNS = (
    "z_rms_velocity_in_s", "z_rms_velocity_mm_s", "temperature_f", "temperature_c",
    "x_rms_velocity_in_s", "x_rms_velocity_mm_s", "z_peak_acceleration_g",
    "x_peak_acceleration_g", "z_peak_vel_comp_freq_hz", "x_peak_vel_comp_freq_hz",
    "z_rms_acceleration_g", "x_rms_acceleration_g", "z_kurtosis", "x_kurtosis",
    "z_crest_factor", "x_crest_factor", "z_peak_velocity_in_s", "z_peak_velocity_mm_s",
    "x_peak_velocity_in_s", "x_peak_velocity_mm_s", "z_high_freq_rms_accel_g",
    "x_high_freq_rms_accel_g", "rpm",
)


def upgrade() -> None:
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fault", sa.String(length=64), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        *[sa.Column(name, sa.Float(), nullable=True) for name in _FEATURE_COLUMNS],
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sensor_readings_family"), "sensor_readings", ["family"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sensor_readings_family"), table_name="sensor_readings")
    op.drop_table("sensor_readings")
