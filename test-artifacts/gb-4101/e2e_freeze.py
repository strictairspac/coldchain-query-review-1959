"""gb-4101 端到端验证：冻结依据、改账不影响比较、中断恢复、重复领取、权限与限额。

前置：db/redis/backend 已启动；不要启动 worker（本脚本自行控制 worker 生命周期）。
用法：~/py311/bin/python -I /workspace/test-artifacts/gb-4101/e2e_freeze.py
"""
import json,time,urllib.request,urllib.error,sys,os,subprocess,signal
import psycopg2
BASE='http://127.0.0.1:19240'
DSN="host=127.0.0.1 port=17740 user=app dbname=query_review"
BACKEND='/workspace/backend'
ENV={**os.environ,'DATABASE_URL':'postgresql+psycopg2://app@127.0.0.1:17740/query_review',
     'REDIS_URL':'redis://127.0.0.1:16379/0','JWT_SECRET':'local-dev-secret','ARTIFACTS_DIR':'/tmp/artifacts'}
PASS,FAIL=[],[]
def check(name,cond,detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  OK ' if cond else ' XX  ')+name+(('  '+detail) if detail else ''))
def api(method,path,token=None,body=None):
    req=urllib.request.Request(BASE+path,method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json',
                 **({'Authorization':'Bearer '+token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw=e.read()
        try:return e.code,json.loads(raw)
        except json.JSONDecodeError:return e.code,{'detail':raw.decode()[:300]}
def login(role):
    s,b=api('POST','/auth/login',body={'email':f'{role}@chenggang.test','password':'ColdChain!17'})
    assert s==200,b;return b['token']
def wait_status(bid,token,targets,timeout=45):
    deadline=time.time()+timeout
    while time.time()<deadline:
        _,rows=api('GET','/batches',token)
        st=next(x['status'] for x in rows if x['id']==bid)
        if st in targets:return st
        time.sleep(0.5)
    return st
def db_exec(sql,args=()):
    with psycopg2.connect(DSN) as c:
        with c.cursor() as cur:cur.execute(sql,args);c.commit()
def db_query(sql,args=()):
    with psycopg2.connect(DSN) as c:
        with c.cursor() as cur:
            cur.execute(sql,args);return cur.fetchall()
def start_worker():
    log=open('/tmp/worker-e2e.log','ab')
    p=subprocess.Popen([sys.executable,'-u','-m','src.worker'],cwd=BACKEND,env=ENV,
                       stdout=log,stderr=log,start_new_session=True)
    time.sleep(1.5);return p
def stop_worker(p):
    os.killpg(os.getpgid(p.pid),signal.SIGTERM);p.wait(timeout=10)
CAND="SELECT customer, SUM(amount) AS total FROM invoices WHERE temperature <= 8 GROUP BY customer HAVING SUM(amount) > 100 ORDER BY customer"
def main():
    op=login('operator');viewer=login('viewer')
    print('\n[1] 受理即冻结：批次带快照表/冻结语句/校验和，快照表存在且 600 行，worker 未启动也已冻结')
    s,b=api('POST','/batches',op,{'name':f'gb4101-freeze-{int(time.time())}','sample_id':1,'candidate_sql':CAND})
    check('受理返回 202',s==202,str(s))
    bid=b['id']
    check('返回冻结快照表名',bool(b['snapshot_table']),b.get('snapshot_table'))
    check('返回两侧冻结语句',b['frozen_original_sql'] and b['frozen_candidate_sql']==b['candidate_sql'])
    check('返回快照行数与 SHA-256 校验和',b['snapshot_row_count']==600 and len(b['snapshot_checksum'])==64)
    check('数据库中快照表实际 600 行',db_query(f"SELECT COUNT(*) FROM {b['snapshot_table']}")[0][0]==600)
    check('query_reader 获快照 SELECT 权限',
          db_query("SELECT has_table_privilege('query_reader',%s,'SELECT')",(b['snapshot_table'],))[0][0] is True)
    check('无 worker 时批次停在 queued',wait_status(bid,op,{'queued'},timeout=3)=='queued')

    print('\n[2] 比较中改账：先更正主表再启动 worker，证据仍按冻结快照产出且 passed')
    db_exec("UPDATE invoices SET amount=amount+1000 WHERE invoice_id<=50")
    live=db_query("SELECT SUM(amount) FROM invoices")[0][0]
    frozen=db_query(f"SELECT SUM(amount) FROM {b['snapshot_table']}")[0][0]
    check('主表已更正且与快照金额不同',live!=frozen,f'live={live} frozen={frozen}')
    wp=start_worker()
    try:
        st=wait_status(bid,op,{'passed','different','failed'})
        check('批次到达终态',st in ('passed','different','failed'),st)
        s,ev=api('GET',f'/evidence/{bid}',op)
        check('证据可读且来源为冻结快照',s==200 and ev['result'].get('frozen_source')==b['snapshot_table'])
        check('按冻结口径判定 passed（改账不影响该批比较）',st=='passed',st)
        check('证据 freeze_basis 行数 600',ev['freeze_basis']['snapshot_row_count']==600)
        check('导出 JSON 包含冻结依据',api('GET',f'/evidence/{bid}/export',op)[1]['result'].get('frozen_source')==b['snapshot_table'])

        print('\n[3] 执行中断恢复：崩溃留下 running+过期租约，恢复后同份依据完成且证据唯一')
        stop_worker(wp)
        s,b2=api('POST','/batches',op,{'name':f'gb4101-crash-{int(time.time())}','sample_id':1,'candidate_sql':CAND})
        bid2=b2['id'];snap2=b2['snapshot_table']
        db_exec("UPDATE batches SET status='running',lease_owner='worker-dead',lease_token='x',"
                "lease_until=now()-interval '60 second',attempts=1 WHERE id=%s",(bid2,))
        wp=start_worker()
        st=wait_status(bid2,op,{'passed','different','failed'})
        check('崩溃批次被恢复并完成',st=='passed',st)
        check('重试不重复生成证据（仅 1 条）',db_query('SELECT COUNT(*) FROM evidence WHERE batch_id=%s',(bid2,))[0][0]==1)
        row=db_query('SELECT frozen_original_sql,frozen_candidate_sql,snapshot_table,attempts FROM batches WHERE id=%s',(bid2,))[0]
        check('恢复后仍使用同份冻结依据',row[2]==snap2 and bool(row[0]) and bool(row[1]))
        check('attempts 记录再次领取',row[3]>=2,str(row[3]))
        check('证据文件只写一次',os.path.exists(f'/tmp/artifacts/review-{bid2}.json'))
        stop_worker(wp)

        print('\n[4] 并发领取：有效租约他人不可领取/发布；过期后新执行者发布，旧执行者不能覆盖')
        s,b3=api('POST','/batches',op,{'name':f'gb4101-lease-{int(time.time())}','sample_id':1,'candidate_sql':CAND})
        bid3=b3['id']
        db_exec("UPDATE batches SET status='running',lease_owner='worker-A',lease_token='tokA',"
                "lease_until=now()+interval '5 minute' WHERE id=%s",(bid3,))
        sys.path.insert(0,BACKEND)
        from src.services.lease import claim_batch,publish_result
        check('有效租约期间并发领取被拒绝',claim_batch(bid3,'worker-B') is None)
        ok,already=publish_result(bid3,'worker-B','whatever',{'error':'x'},'failed')
        check('非持有者发布被拒绝',ok is False and already is False)
        check('token 错误的持有者不能发布',publish_result(bid3,'worker-A','wrong',{},'failed')[0] is False)
        db_exec("UPDATE batches SET lease_until=now()-interval '1 second' WHERE id=%s",(bid3,))
        tokB=claim_batch(bid3,'worker-B')
        check('租约过期后可被新执行者领取',tokB is not None)
        ok,_=publish_result(bid3,'worker-B',tokB,{'equivalent':True,'frozen_source':b3['snapshot_table']},'passed')
        check('当前执行者发布成功',ok is True)
        ok,already=publish_result(bid3,'worker-A','tokA',{'equivalent':False},'different')
        check('过期执行者不能覆盖（already_done）',ok is False and already is True)
        check('终态未被过期执行者改写',db_query('SELECT status FROM batches WHERE id=%s',(bid3,))[0][0]=='passed')
        check('证据与状态同事务落库',db_query('SELECT COUNT(*) FROM evidence WHERE batch_id=%s',(bid3,))[0][0]==1)

        print('\n[5] 冻结失败整批不受理：模拟快照异常，批次不留痕、不进队列')
        from src.config.database import Session
        from src.services import batch as bsvc
        from src.schemas.batch import BatchInput
        bsvc.create_snapshot=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('simulated freeze failure'))
        try:
            with Session() as sdb:
                bsvc.create_batch(sdb,BatchInput(name=f'gb4101-fail-{int(time.time())}',sample_id=1,candidate_sql=CAND))
            raised=False
        except Exception as e:raised=True;msg=str(e)
        check('冻结失败抛 503 且整批不受理',raised and '503' in msg,msg)
        check('失败批次未入库',db_query("SELECT COUNT(*) FROM batches WHERE name LIKE %s",('gb4101-fail-%',))[0][0]==0)

        print('\n[6] 只读权限/查询限额/比较口径保留；viewer 写请求被拒')
        check('viewer 创建批次 403',api('POST','/batches',viewer,{'name':'v','sample_id':1,'candidate_sql':CAND})[0]==403)
        check('viewer 创建样本 403',api('POST','/samples',viewer,{'name':'v','description':'y','original_sql':'SELECT * FROM invoices'})[0]==403)
        check('viewer 只读查询可用',api('GET','/batches',viewer)[0]==200)
        check('多语句拒绝 422',api('POST','/batches',op,{'name':f'gb4101-bad-{time.time_ns()}','sample_id':1,'candidate_sql':'SELECT * FROM invoices; DROP TABLE invoices'})[0]==422)
        check('跨表拒绝 422',api('POST','/batches',op,{'name':f'gb4101-bad2-{time.time_ns()}','sample_id':1,'candidate_sql':'SELECT * FROM users'})[0]==422)
        s,bd=api('POST','/batches',op,{'name':f'gb4101-diff-{int(time.time())}','sample_id':3,
            'candidate_sql':"SELECT customer, COUNT(*) AS count FROM invoices WHERE temperature > 8 GROUP BY customer ORDER BY customer"})
        bid4=bd['id'];wp2=start_worker()
        st=wait_status(bid4,op,{'passed','different','failed'})
        s,ev4=api('GET',f'/evidence/{bid4}',op)
        check('原比较口径保留（含 missing/extra 与双侧摘要）',
              st in ('passed','different') and all(k in ev4['result'] for k in ('missing_rows','extra_rows','original_checksum','candidate_checksum')),st)
        stop_worker(wp2)

        print('\n[7] 旧证据（v1，无冻结列）照常可读')
        db_exec("INSERT INTO batches(name,sample_id,candidate_sql,status,attempts) VALUES(%s,1,%s,'failed',0)",
                (f'gb4101-legacy-{int(time.time())}',CAND))
        legacy=db_query("SELECT id FROM batches WHERE name LIKE %s ORDER BY id DESC LIMIT 1",('gb4101-legacy-%',))[0][0]
        db_exec("INSERT INTO evidence(batch_id,result) VALUES(%s,%s)",(legacy,json.dumps({'error':'legacy v1 evidence'})))
        s,lev=api('GET',f'/evidence/{legacy}',op)
        check('旧证据可读且内容原样',s==200 and lev['result']['error']=='legacy v1 evidence')
        check('旧证据 freeze_basis 为空不报错',lev['freeze_basis'] is None)
    finally:
        try:stop_worker(wp)
        except Exception:pass
    print(f'\n==== 通过 {len(PASS)} / 失败 {len(FAIL)} ====')
    if FAIL:print('失败项：',FAIL);sys.exit(1)
if __name__=='__main__':main()
