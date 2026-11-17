from fastapi import HTTPException
from sqlalchemy import select
from ..models.evidence import Evidence
from ..models.batch import Batch
def _freeze_basis(db,batch_id):
    b=db.get(Batch,batch_id)
    if not b or not b.snapshot_table:return None  # 旧证据（v1）无冻结依据
    return {'snapshot_table':b.snapshot_table,'frozen_original_sql':b.frozen_original_sql,
            'frozen_candidate_sql':b.frozen_candidate_sql,'snapshot_row_count':b.snapshot_row_count,
            'snapshot_checksum':b.snapshot_checksum,'frozen_at':str(b.frozen_at) if b.frozen_at else None,
            'attempts':b.attempts}
def _row(db,x):
    return {'id':x.id,'batch_id':x.batch_id,'result':x.result,'freeze_basis':_freeze_basis(db,x.batch_id)}
def list_evidence(db):
    return [_row(db,x) for x in db.scalars(select(Evidence).order_by(Evidence.id.desc()))]
def get_evidence(db,batch_id):
    x=db.scalar(select(Evidence).where(Evidence.batch_id==batch_id))
    if not x:raise HTTPException(404,'证据尚未生成，请等待 worker 完成')
    # 旧证据（v1，无冻结列）照常可读：freeze_basis 字段为 None，result 内容原样返回
    return _row(db,x)
