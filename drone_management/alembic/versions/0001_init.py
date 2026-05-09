"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drones",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("system_id", sa.Integer, nullable=False, unique=True),
        sa.Column("component_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default="drone"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_drones_system_id", "drones", ["system_id"])

    op.create_table(
        "telemetry_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drone_id", sa.Integer, sa.ForeignKey("drones.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lat", sa.Float), sa.Column("lon", sa.Float), sa.Column("alt_m", sa.Float),
        sa.Column("rel_alt_m", sa.Float), sa.Column("heading_deg", sa.Float),
        sa.Column("vx", sa.Float), sa.Column("vy", sa.Float), sa.Column("vz", sa.Float),
        sa.Column("roll", sa.Float), sa.Column("pitch", sa.Float), sa.Column("yaw", sa.Float),
        sa.Column("battery_voltage", sa.Float), sa.Column("battery_remaining", sa.Integer),
        sa.Column("gps_fix_type", sa.Integer), sa.Column("satellites", sa.Integer),
        sa.Column("mode", sa.String(32)), sa.Column("armed", sa.Boolean),
    )
    op.create_index("ix_telemetry_records_drone_id", "telemetry_records", ["drone_id"])
    op.create_index("ix_telemetry_drone_ts", "telemetry_records", ["drone_id", sa.text("ts DESC")])

    op.create_table(
        "commands",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drone_id", sa.Integer, sa.ForeignKey("drones.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("params_json", sa.String, nullable=False, server_default="{}"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ack_status", sa.String(16)),
        sa.Column("ack_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_commands_drone_id", "commands", ["drone_id"])


def downgrade() -> None:
    op.drop_index("ix_commands_drone_id", table_name="commands")
    op.drop_table("commands")
    op.drop_index("ix_telemetry_drone_ts", table_name="telemetry_records")
    op.drop_index("ix_telemetry_records_drone_id", table_name="telemetry_records")
    op.drop_table("telemetry_records")
    op.drop_index("ix_drones_system_id", table_name="drones")
    op.drop_table("drones")
