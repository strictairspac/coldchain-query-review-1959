"""幂等 schema 维护：metadata 建表 + 旧库补列（v1 → v2 冻结/租约列）。"""
from sqlalchemy import text
from .database import engine,Base
# 引入全部模型，保证 metadata 完整
from ..models import user,sample,batch,evidence,audit  # noqa: F401
_ADDED_COLUMNS={
    'batches':{
        'snapshot_table':'VARCHAR(120)',
        'frozen_original_sql':'TEXT',
        'frozen_candidate_sql':'TEXT',
        'snapshot_row_count':'INTEGER',
        'snapshot_checksum':'VARCHAR(64)',
        'frozen_at':'TIMESTAMP',
        'lease_owner':'VARCHAR(80)',
        'lease_token':'VARCHAR(64)',
        'lease_until':'TIMESTAMP',
        'attempts':'INTEGER NOT NULL DEFAULT 0',
    },
}
def ensure_schema():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table,columns in _ADDED_COLUMNS.items():
            existing={r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name=:t"),{'t':table})}
            for name,ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
