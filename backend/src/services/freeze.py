"""复核受理时的账单冻结：为每个批次建立只读快照表，后续更正不影响该批比较。

冻结期间 invoices 仍可正常写账：快照是独立的完整副本，不持有原表锁。
冻结失败由调用方回滚整批受理（批次不留痕、不进队列）。
"""
import hashlib
from datetime import datetime,timezone
from sqlalchemy import text
from ..config.database import engine
from ..constants.enums import SNAPSHOT_TABLE

def _checksum_rows(rows):
    # 与比较口径一致：按列位置的数据库文本值，NULL 保留为空值
    lines=[]
    for row in rows:
        lines.append('|'.join('' if v is None else str(v) for v in row))
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()

def create_snapshot(batch_id):
    """在单事务内复制 invoices 到快照表并授权只读角色。

    返回 (snapshot_table, row_count, checksum)。任何失败抛出异常，
    由上层整批回滚——冻结失败整批不受理。
    """
    table=SNAPSHOT_TABLE(batch_id)
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {table}'))
        # 完整结构与数据复制；不带约束/序列（避免 PK 序列冲突），快照只读、只增不改
        conn.execute(text(f'CREATE TABLE {table} (LIKE invoices INCLUDING DEFAULTS INCLUDING INDEXES)'))
        conn.execute(text(f'INSERT INTO {table} SELECT * FROM invoices'))
        conn.execute(text(f'GRANT SELECT ON {table} TO query_reader'))
        count=conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
        rows=conn.execute(text(f'SELECT * FROM {table} ORDER BY invoice_id')).all()
        checksum=_checksum_rows(rows)
    return table,count,checksum

def drop_snapshot(batch_id):
    table=SNAPSHOT_TABLE(batch_id)
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {table}'))

def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)
