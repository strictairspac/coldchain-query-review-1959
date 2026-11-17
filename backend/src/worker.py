import json,time,traceback,os
from pathlib import Path
from .config.database import Session
from .models.batch import Batch
from .models.evidence import Evidence
from .services.batch import queue
from .services.query_engine import compare
from .services.lease import new_worker_id,claim_batch,publish_result,recoverable_batches
from sqlalchemy import select
ARTIFACTS=Path(os.environ.get('ARTIFACTS_DIR','/artifacts'))
heartbeat=ARTIFACTS/'worker.heartbeat'
WORKER_ID=new_worker_id()
def _write_artifact(batch_id,result):
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    # 重试不重复生成证据：同一批次固定文件名，内容只写一次（由 publish 保证）
    path=ARTIFACTS/f'review-{batch_id}.json'
    if not path.exists():
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
def run_one(batch_id):
    # 并发领取：只有成功取得有效租约的执行者继续
    token=claim_batch(batch_id,WORKER_ID)
    if not token:return
    with Session() as db:
        batch=db.get(Batch,batch_id)
        if not batch or db.scalar(select(Evidence).where(Evidence.batch_id==batch_id)):return
        # 同份依据：始终使用受理时冻结的快照与两侧语句，恢复后重试口径不变
        original=batch.frozen_original_sql
        candidate=batch.frozen_candidate_sql
        snapshot=batch.snapshot_table
    try:
        # 测试钩子：WORKER_DELAY_SECONDS 仅用于中断恢复演练，默认关闭
        delay=float(os.environ.get('WORKER_DELAY_SECONDS','0') or 0)
        if delay>0:time.sleep(delay)
        result=compare(original,candidate,snapshot)
        status='passed' if result['equivalent'] else 'different'
    except Exception as exc:
        result={'error':str(exc)[:500],'frozen_source':snapshot}
        status='failed'
    ok,already=publish_result(batch_id,WORKER_ID,token,result,status)
    if ok:_write_artifact(batch_id,result)
    # already=True 表示证据已由先前执行生成；过期执行者 ok=False，不能覆盖
def main():
    while True:
        try:
            heartbeat.parent.mkdir(parents=True,exist_ok=True)
            heartbeat.write_text(str(time.time()))
            item=queue.blpop('query-review:jobs',timeout=2)
            if item:
                run_one(int(item[1]))
            else:
                # 执行中断恢复：扫描 queued/running（含崩溃过期租约），按同份冻结依据重试
                for ident in recoverable_batches():run_one(ident)
        except Exception:
            traceback.print_exc();time.sleep(2)
if __name__=='__main__':
    main()
