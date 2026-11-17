"""gb-4101 并发领取压力测试：N 个执行者同时领取同一批次，仅一人成功且证据唯一。"""
import sys,threading,time
sys.path.insert(0,'/workspace/backend')
import psycopg2
from src.config.database import Session
from src.models.batch import Batch
from src.services.lease import claim_batch,publish_result,new_worker_id
DSN="host=127.0.0.1 port=17740 user=app dbname=query_review"
CAND="SELECT customer, COUNT(*) FROM invoices GROUP BY customer"
def setup_batch():
    with psycopg2.connect(DSN) as c:
        with c.cursor() as cur:
            cur.execute("INSERT INTO batches(name,sample_id,candidate_sql,status,attempts) "
                        "VALUES(%s,1,%s,'queued',0) RETURNING id",
                        (f'gb4101-stress-{time.time_ns()}',CAND))
            return cur.fetchone()[0]
def main():
    bid=setup_batch()
    results=[];lock=threading.Lock()
    def worker():
        wid=new_worker_id()
        token=claim_batch(bid,wid)
        with lock:results.append((wid,token is not None))
        if token:
            ok,_=publish_result(bid,wid,token,{'equivalent':True},'passed')
            with lock:results.append(('publish-'+wid,ok))
    threads=[threading.Thread(target=worker) for _ in range(12)]
    for t in threads:t.start()
    for t in threads:t.join()
    claims=[r for r in results if r[1] and not r[0].startswith('publish-')]
    publishes=[r for r in results if r[0].startswith('publish-')]
    with psycopg2.connect(DSN) as c:
        with c.cursor() as cur:
            cur.execute("SELECT status,attempts,lease_owner FROM batches WHERE id=%s",(bid,));status,attempts,owner=cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM evidence WHERE batch_id=%s",(bid,));ev=cur.fetchone()[0]
    print('成功领取数 =',len(claims),'(期望 1)')
    print('成功发布数 =',len([p for p in publishes if p[1]]),'(期望 1)')
    print('DB 状态 =',status,' attempts =',attempts,' 证据数 =',ev)
    assert len(claims)==1,'并发领取必须只有一人成功'
    assert len([p for p in publishes if p[1]])==1
    assert status=='passed' and attempts==1 and ev==1
    print('CONCURRENCY STRESS OK')
if __name__=='__main__':main()
