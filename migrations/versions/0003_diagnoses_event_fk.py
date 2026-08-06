"""diagnoses_event_fk

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove diagnosticos orfaos legados (event_id sem Event correspondente)
    # ANTES de criar a foreign key -- bancos que passaram pelo bug do duplo
    # commit (Event commitado, Diagnosis falhou) podem ter esses orfaos, e a
    # constraint abaixo falharia ao ser criada contra dados inconsistentes.
    op.execute("DELETE FROM diagnoses WHERE event_id NOT IN (SELECT id FROM events)")

    # batch_alter_table funciona em Postgres (ALTER TABLE direto) e SQLite
    # (recreate automatico da tabela) com o mesmo codigo de migration.
    with op.batch_alter_table("diagnoses") as batch_op:
        batch_op.create_foreign_key(
            "fk_diagnoses_event_id", "events", ["event_id"], ["id"]
        )
        batch_op.create_index("ix_diagnoses_event_id", ["event_id"])


def downgrade() -> None:
    with op.batch_alter_table("diagnoses") as batch_op:
        batch_op.drop_index("ix_diagnoses_event_id")
        batch_op.drop_constraint("fk_diagnoses_event_id", type_="foreignkey")
