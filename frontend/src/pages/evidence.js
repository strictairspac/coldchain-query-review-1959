import{evidence}from'../stores/evidence.js';import{getEvidence,exportEvidence}from'../api/evidence.js';import{header}from'../components/common/header.js';import{table}from'../components/common/table.js';import{badge}from'../components/common/badge.js';import{esc,json}from'../utils/html.js';import{notify}from'../hooks/feedback.js';
function freezePanel(ev){
  const f=ev.freeze_basis;
  if(!f)return '<section class="panel subtle"><h2>冻结依据</h2><p class="muted">该证据为旧版批次生成，无受理时冻结；结果按当时的 invoices 实时数据执行，旧证据照常可读。</p></section>';
  return `<section class="panel"><div class="actions" style="margin-top:0"><h2 style="margin:0">冻结依据（受理时点）</h2><span class="badge frozen">账单已冻结</span></div>
  <div class="metrics">
    <div><small>冻结快照表</small><strong style="font-size:15px">${esc(f.snapshot_table)}</strong></div>
    <div><small>快照行数</small><strong>${f.snapshot_row_count}</strong></div>
    <div><small>重试领取次数</small><strong>${f.attempts ?? 0}</strong></div>
  </div>
  <p class="helper">冻结时间：${esc((f.frozen_at||'').slice(0,19))}　·　快照 SHA-256：<span class="mono">${esc(f.snapshot_checksum)}</span><br>受理后对 invoices 的更正不影响本批比较；冻结期间账单仍可正常写账。</p>
  <div class="split">
    <div><label>冻结的原始语句</label><pre class="json">${esc(f.frozen_original_sql)}</pre></div>
    <div><label>冻结的候选语句（实际计划基于此语句）</label><pre class="json">${esc(f.frozen_candidate_sql)}</pre></div>
  </div></section>`;
}
export async function evidencePage(el){
  const records=await evidence.load();
  const ident=Number(location.hash.split('/')[1])||records[0]?.batch_id;
  const detail=ident?await getEvidence(ident):null;
  const r=detail?.result;
  el.innerHTML=header('04','从冻结依据一直查到实际执行计划','证据来源于 PostgreSQL 对冻结快照的实际执行。呈现受理时冻结的两侧语句、快照校验信息，以及两侧真实 EXPLAIN ANALYZE 计划，供结算复核人独立检查。')
  +`<section class="panel"><label>选择复核证据</label><select id="choose"><option value="">请选择已完成批次</option>${records.map(x=>`<option value="${x.batch_id}" ${x.batch_id===ident?'selected':''}>批次 #${x.batch_id} · ${x.result.error?'执行失败':x.result.equivalent?'结果一致':'存在差异'}${x.freeze_basis?' · 已冻结':''}</option>`).join('')}</select></section>`
  +(detail?freezePanel(detail):'')
  +(r?`<section class="panel"><div class="actions" style="margin-top:0"><h2 style="margin:0">复核批次 #${ident}</h2>${badge(r.error?'failed':r.equivalent?'passed':'different')}<button id="export">下载 JSON 证据 ↓</button></div>
  ${r.frozen_source?`<p class="helper">两侧查询实际读取冻结表 <span class="mono">${esc(r.frozen_source)}</span>，而非实时 invoices。</p>`:''}
  ${r.error?'<p class="error">'+esc(r.error)+'</p>':`<div class="metrics"><div><small>原始结果行数</small><strong>${r.original.row_count}</strong></div><div><small>候选结果行数</small><strong>${r.candidate.row_count}</strong></div><div><small>原始 / 候选查询耗时 ms</small><strong>${r.original.elapsed_ms} / ${r.candidate.elapsed_ms}</strong></div></div>
  <p class="helper">${esc(r.comparison)}<br>${esc(r.note)}</p>
  <div class="split"><div><h2>候选实际结果</h2>${table(r.candidate.columns,r.candidate.rows.slice(0,20).map(row=>row.map(esc)))}<p class="helper">最多预览20行，完整结果在 JSON 中。</p><h2>差异定位</h2><pre class="json">${json({missing_rows:r.missing_rows,extra_rows:r.extra_rows})}</pre></div>
  <aside><h2>结果摘要 SHA-256</h2><pre class="json">原始：${esc(r.original_checksum)}
候选：${esc(r.candidate_checksum)}</pre>
  <details open><summary>候选实际 EXPLAIN ANALYZE 计划</summary><pre class="json">${json(r.candidate.plan)}</pre></details>
  <details><summary>原始实际 EXPLAIN ANALYZE 计划</summary><pre class="json">${json(r.original.plan)}</pre></details></aside></div>`}</section>`
  :'<div class="empty">还没有执行证据。到 SQL 复核页提交一份候选 SQL，worker 完成后在这里查看。</div>');
  el.querySelector('#choose').onchange=e=>{if(e.target.value)location.hash='evidence/'+e.target.value};
  const b=el.querySelector('#export');
  if(b)b.onclick=()=>exportEvidence(ident).catch(e=>notify(e.message));
}
