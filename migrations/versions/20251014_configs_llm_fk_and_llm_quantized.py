"""
configs: replace name/quant flags with LLM FKs; llms: add is_quantized

- Add columns configs.llm_id, configs.qa_llm_id (nullable, FK llms.id)
- Add column llms.is_quantized (nullable)
- Backfill llm_id/qa_llm_id from existing name columns when possible
- Drop configs.llm_name, configs.is_quantized, configs.qa_llm_name, configs.qa_is_quantized

Idempotent and inspector-guarded for Postgres/SQLite.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20251014_configs_llm_fk_and_llm_quantized'
down_revision = '20251009_drop_service_value'
branch_labels = None
depends_on = None


def column_exists(conn, table, column):
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns(table)]
    return column in cols


def constraint_exists(conn, name):
    try:
        res = conn.execute(sa.text("SELECT 1 FROM information_schema.table_constraints WHERE constraint_name=:n"), {"n": name})
        return res.first() is not None
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    conn = bind.connect()

    # Add llms.is_quantized if missing
    if not column_exists(conn, 'llms', 'is_quantized'):
        op.add_column('llms', sa.Column('is_quantized', sa.Boolean(), nullable=True))

    # Add configs.llm_id, configs.qa_llm_id
    if not column_exists(conn, 'configs', 'llm_id'):
        op.add_column('configs', sa.Column('llm_id', sa.Integer(), nullable=True))
    if not column_exists(conn, 'configs', 'qa_llm_id'):
        op.add_column('configs', sa.Column('qa_llm_id', sa.Integer(), nullable=True))

    # Create FKs if not exist (Postgres path)
    try:
        if not constraint_exists(conn, 'fk_configs_llm_id_llms'):
            op.create_foreign_key('fk_configs_llm_id_llms', 'configs', 'llms', ['llm_id'], ['id'], ondelete=None)
        if not constraint_exists(conn, 'fk_configs_qa_llm_id_llms'):
            op.create_foreign_key('fk_configs_qa_llm_id_llms', 'configs', 'llms', ['qa_llm_id'], ['id'], ondelete=None)
    except Exception:
        # SQLite: will ignore named constraints
        pass

    # Backfill: map names to ids if legacy columns present
    insp = sa.inspect(conn)
    config_cols = [c['name'] for c in insp.get_columns('configs')]
    if 'llm_name' in config_cols:
        # Assume LLM.name holds the human-readable name in previous sync
        conn.execute(sa.text("""
            UPDATE configs c
            SET llm_id = (
                SELECT l.id FROM llms l WHERE l.name = c.llm_name LIMIT 1
            )
            WHERE c.llm_id IS NULL AND c.llm_name IS NOT NULL
        """))
    if 'qa_llm_name' in config_cols:
        conn.execute(sa.text("""
            UPDATE configs c
            SET qa_llm_id = (
                SELECT l.id FROM llms l WHERE l.name = c.qa_llm_name LIMIT 1
            )
            WHERE c.qa_llm_id IS NULL AND c.qa_llm_name IS NOT NULL
        """))

    # Drop legacy columns if exist
    for col in ['is_quantized', 'llm_name', 'qa_is_quantized', 'qa_llm_name']:
        if column_exists(conn, 'configs', col):
            try:
                op.drop_column('configs', col)
            except Exception:
                pass


def downgrade():
    bind = op.get_bind()
    conn = bind.connect()

    # Recreate legacy columns
    for col, typ in [
        ('is_quantized', sa.Boolean()),
        ('llm_name', sa.String()),
        ('qa_is_quantized', sa.Boolean()),
        ('qa_llm_name', sa.String()),
    ]:
        if not column_exists(conn, 'configs', col):
            op.add_column('configs', sa.Column(col, typ, nullable=True))

    # Best-effort backfill names from llm relations
    conn.execute(sa.text("""
        UPDATE configs c SET llm_name = (
            SELECT l.name FROM llms l WHERE l.id = c.llm_id LIMIT 1
        ) WHERE c.llm_id IS NOT NULL AND c.llm_name IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE configs c SET qa_llm_name = (
            SELECT l.name FROM llms l WHERE l.id = c.qa_llm_id LIMIT 1
        ) WHERE c.qa_llm_id IS NOT NULL AND c.qa_llm_name IS NULL
    """))

    # Drop FKs and new columns
    try:
        op.drop_constraint('fk_configs_llm_id_llms', 'configs', type_='foreignkey')
        op.drop_constraint('fk_configs_qa_llm_id_llms', 'configs', type_='foreignkey')
    except Exception:
        pass

    for col in ['llm_id', 'qa_llm_id']:
        if column_exists(conn, 'configs', col):
            try:
                op.drop_column('configs', col)
            except Exception:
                pass

    # Remove llms.is_quantized
    if column_exists(conn, 'llms', 'is_quantized'):
        try:
            op.drop_column('llms', 'is_quantized')
        except Exception:
            pass
