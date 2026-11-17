"""执行者租约：并发领取只允许当前执行者发布，过期执行者不能覆盖。

所有领取/发布均为单条条件 UPDATE（行锁 + WHERE 条件），在数据库层原子完成，
不依赖应用层先读后写，避免并发下的丢失更新。
"""
import secrets
from datetime import timedelta
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from ..config.database import Session
from ..constants.enums import LEASE_SECONDS,TERMINAL_STATUSES
# 显式引入关联模型，保证独立进程中 ORM 外键映射完整
from ..models.sample import Sample  # noqa: F401
from ..models.batch import Batch
from ..models.evidence import Evidence
from .freeze import now_utc
def new_worker_id():
    return 'worker-'+secrets.token_hex(8)
def claim_batch(batch_id,worker_id):
    """原子领取一个批次。成功返回租约 token，否则返回 None。

    条件：未到终态且（无租约 / 租约已过期 / 本人续租）。
    单条条件 UPDATE 由行锁串行化，同一时刻只有一个执行者领取成功；
    崩溃执行者的租约到期后，恢复流程可重新领取，重试不重复生成证据。
    """
    token=secrets.token_hex(16)
    now=now_utc();until=now+timedelta(seconds=LEASE_SECONDS)
    with Session() as db:
        rowcount=db.execute(text('''
            UPDATE batches SET lease_owner=:owner, lease_token=:token,
                   lease_until=:until, status='running', attempts=attempts+1
            WHERE id=:bid AND status NOT IN ('passed','different','failed')
              AND (lease_until IS NULL OR lease_until<=:now OR lease_owner=:owner)
        '''),{'owner':worker_id,'token':token,'until':until,'now':now,'bid':batch_id}).rowcount
        db.commit()
    return token if rowcount==1 else None
def publish_result(batch_id,worker_id,token,result,status):
    """只有持有有效租约的当前执行者可发布；完成状态与证据在同一事务原子切换。

    返回 (ok, already_done)。过期/被取代的执行者不能覆盖；
    已有证据的批次不重复生成。
    """
    now=now_utc()
    with Session() as db:
        batch=db.get(Batch,batch_id)
        if not batch:return False,False
        if batch.status in TERMINAL_STATUSES:
            return False,True
        if batch.lease_owner!=worker_id or batch.lease_token!=token or not batch.lease_until or batch.lease_until<=now:
            return False,False  # 过期执行者不能覆盖
        if db.scalar(select(Evidence).where(Evidence.batch_id==batch_id)):
            return False,True
        try:
            # 原子切换：证据插入与批次终态在同一事务提交
            db.add(Evidence(batch_id=batch_id,result=result))
            db.flush()
            updated=db.execute(text('''
                UPDATE batches SET status=:status, lease_until=:now
                WHERE id=:bid AND lease_owner=:owner AND lease_token=:token
                  AND lease_until>:now AND status NOT IN ('passed','different','failed')
            '''),{'status':status,'now':now,'bid':batch_id,'owner':worker_id,'token':token}).rowcount
            if updated!=1:
                db.rollback();return False,False
            db.commit()
            return True,False
        except IntegrityError:
            # 并发下唯一约束兜底：每批证据至多一条
            db.rollback();return False,True
def recoverable_batches():
    """恢复扫描：待执行或执行中（含崩溃留下的过期租约）的批次。"""
    with Session() as db:
        return list(db.scalars(select(Batch.id).where(Batch.status.in_(['queued','running'])).order_by(Batch.id)))
