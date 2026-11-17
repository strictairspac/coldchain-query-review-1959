"""gb-4101 真实中断恢复：worker 被 SIGKILL 后，新 worker 用同份冻结依据完成且证据唯一。"""
import json,os,signal,subprocess,sys,time,urllib.request,urllib.error
BASE='http://127.0.0.1:19240';BACKEND='/workspace/backend'
ENV={**os.environ,'DATABASE_URL':'postgresql+psycopg2://app@127.0.0.1:17740/query_review',
     'REDIS_URL':'redis://127.0.0.1:16379/0','JWT_SECRET':'local-dev-secret','ARTIFACTS_DIR':'/tmp/artifacts'}
def api(method,path,token=None,body=None):
    req=urllib.request.Request(BASE+path,method=method,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def wait(bid,tok,states,timeout=40):
    end=time.time()+timeout
    while time.time()<end:
        _,rows=api('GET','/batches',tok);st=next(x['status'] for x in rows if x['id']==bid)
        if st in states:return st
        time.sleep(0.4)
    return st
def main():
    tok=api('POST','/auth/login',body={'email':'operator@chenggang.test','password':'ColdChain!17'})[1]['token']
    s,b=api('POST','/batches',tok,{'name':f'gb4101-sigkill-{time.time_ns()}','sample_id':1,
        'candidate_sql':"SELECT customer, SUM(amount) AS total FROM invoices WHERE temperature <= 8 GROUP BY customer HAVING SUM(amount) > 100 ORDER BY customer"})
    assert s==202,s;bid=b['id'];snap=b['snapshot_table']
    print('批次',bid,'已冻结于',snap)
    log=open('/tmp/worker-crash.log','ab')
    crash_env={**ENV,'WORKER_DELAY_SECONDS':'5'}
    p=subprocess.Popen([sys.executable,'-u','-m','src.worker'],cwd=BACKEND,env=crash_env,stdout=log,stderr=log,start_new_session=True)
    time.sleep(2.5)  # 领取后、compare 睡眠中强杀（模拟执行中断）
    os.killpg(os.getpgid(p.pid),signal.SIGKILL);p.wait()
    print('worker 已 SIGKILL（compare 进行中）')
    st=wait(bid,tok,{'running'})
    _,rows=api('GET','/batches',tok);row=next(x for x in rows if x['id']==bid)
    print('中断后状态 =',st,' 租约持有者 =',row['lease_owner'],' 领取次数 =',row['attempts'])
    assert st=='running' and row['attempts']==1
    p2=subprocess.Popen([sys.executable,'-u','-m','src.worker'],cwd=BACKEND,env=ENV,
                        stdout=open('/tmp/worker-recover.log','ab'),stderr=subprocess.STDOUT,start_new_session=True)
    try:
        st=wait(bid,tok,{'passed','different','failed'},timeout=45)
        print('恢复后终态 =',st)
        assert st=='passed'
        s,ev=api('GET',f'/evidence/{bid}',tok)
        assert s==200 and ev['result']['frozen_source']==snap
        assert ev['freeze_basis']['snapshot_table']==snap
        _,rows=api('GET','/batches',tok);row=next(x for x in rows if x['id']==bid)
        print('恢复后领取次数 =',row['attempts'],' 证据来源 =',ev['result']['frozen_source'])
        assert row['attempts']==2
        import psycopg2
        with psycopg2.connect("host=127.0.0.1 port=17740 user=app dbname=query_review") as c:
            with c.cursor() as cur:
                cur.execute('SELECT count(*) FROM evidence WHERE batch_id=%s',(bid,));n=cur.fetchone()[0]
        assert n==1,n
        assert os.path.exists(f'/tmp/artifacts/review-{bid}.json')
        print('SIGKILL 恢复测试 OK：同份依据、证据唯一、attempts=2')
    finally:
        os.killpg(os.getpgid(p2.pid),signal.SIGTERM)
if __name__=='__main__':main()
