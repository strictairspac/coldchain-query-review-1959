from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select,text
from ..config.settings import REDIS_URL
from ..models.batch import Batch
from ..models.sample import Sample
from .query_engine import validate_sql
from .freeze import create_snapshot,drop_snapshot,now_utc
queue=Redis.from_url(REDIS_URL)
# 幂等入队：同一批次在队列中只保留一个 job，避免恢复/重试产生重复消息
_ENQUEUE=queue.register_script(
    "if redis.call('lpos',KEYS[1],ARGV[1])==false then return redis.call('rpush',KEYS[1],ARGV[1]) else return 0 end")
def enqueue(batch_id):
    _ENQUEUE(keys=['query-review:jobs'],args=[batch_id])
def serialize(x):
    return {'id':x.id,'name':x.name,'sample_id':x.sample_id,'candidate_sql':x.candidate_sql,
            'status':x.status,'created_at':str(x.created_at),
            'snapshot_table':x.snapshot_table,'frozen_original_sql':x.frozen_original_sql,
            'frozen_candidate_sql':x.frozen_candidate_sql,'snapshot_row_count':x.snapshot_row_count,
            'snapshot_checksum':x.snapshot_checksum,'frozen_at':str(x.frozen_at) if x.frozen_at else None,
            'lease_owner':x.lease_owner,'lease_until':str(x.lease_until) if x.lease_until else None,
            'attempts':x.attempts}
def list_batches(db):
    return [serialize(x) for x in db.scalars(select(Batch).order_by(Batch.id.desc()))]
def create_batch(db,data):
    candidate=validate_sql(data.candidate_sql)
    sample=db.get(Sample,data.sample_id)
    if not sample:raise HTTPException(404,'样本不存在')
    original=validate_sql(sample.original_sql)
    # 串行化受理：并发创建时名称查重与 20 任务限额口径一致
    db.execute(text('SELECT pg_advisory_xact_lock(4101)'))
    if db.scalar(select(Batch).where(Batch.name==data.name)):raise HTTPException(409,'批次名称已存在')
    if len(list(db.scalars(select(Batch).where(Batch.status.in_(['queued','running'])))))>=20:
        raise HTTPException(429,'待执行任务达到20个，请稍后重试')
    obj=Batch(name=data.name,sample_id=data.sample_id,candidate_sql=candidate,status='queued')
    db.add(obj);db.flush()  # 取得 batch_id 供快照命名
    # 复核受理即冻结：账单快照 + 两侧冻结语句同事务落库；冻结失败整批回滚不受理
    try:
        snapshot_table,row_count,checksum=create_snapshot(obj.id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(503,'账单冻结失败，整批不受理：'+str(exc)[:200])
    obj.snapshot_table=snapshot_table
    obj.frozen_original_sql=original
    obj.frozen_candidate_sql=candidate
    obj.snapshot_row_count=row_count
    obj.snapshot_checksum=checksum
    obj.frozen_at=now_utc()
    try:
        db.commit()
    except Exception:
        drop_snapshot(obj.id)  # 业务事务失败则清理已建快照，避免孤儿表
        raise
    enqueue(obj.id)
    return serialize(obj)
