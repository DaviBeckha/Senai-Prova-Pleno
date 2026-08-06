"""documents_unique_family_title

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicatas exatas legadas (family+title identicos, comparacao
    # case-sensitive -- mesmo criterio da constraint abaixo) da race
    # select-then-insert do register() antigo, mantendo a linha mais antiga
    # (menor id) de cada grupo. Sem isso, criar a constraint falharia contra
    # dados legados inconsistentes.
    op.execute(
        "DELETE FROM documents WHERE id NOT IN "
        "(SELECT MIN(id) FROM documents GROUP BY family, title)"
    )

    # batch_alter_table funciona em Postgres (ALTER TABLE direto) e SQLite
    # (recreate automatico da tabela) com o mesmo codigo de migration.
    with op.batch_alter_table("documents") as batch_op:
        batch_op.create_unique_constraint(
            "uq_documents_family_title", ["family", "title"]
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_family_title", type_="unique")
