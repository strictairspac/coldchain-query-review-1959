import{batches}from'../stores/batch.js';import{header}from'../components/common/header.js';import{table}from'../components/common/table.js';import{badge}from'../components/common/badge.js';import{esc}from'../utils/html.js';
function freezeCell(x){
  if(!x.snapshot_table)return '<span class="muted">旧版批次 · 无冻结</span>';
  return `<span class="badge frozen">账单已冻结</span><br><span class="mono muted" style="font-size:11px">${esc(x.snapshot_table)}<br>${x.snapshot_row_count} 行 · ${esc((x.frozen_at||'').slice(0,19))}</span>`;
}
function leaseCell(x){
  if(['passed','different','failed'].includes(x.status))return esc('共领取 '+(x.attempts||0)+' 次');
  const owner=x.lease_owner?esc(x.lease_owner):'等待领取';
  return `<span class="mono" style="font-size:11px">${owner}</span><br><span class="muted" style="font-size:11px">租约至 ${x.lease_until?esc(x.lease_until.slice(11,19)):'—'}</span>`;
}
export async function historyPage(el){
  const rows=await batches.load();
  el.innerHTML=header('03','运行记录按批次留痕','任务由 Redis 分发到独立 worker；受理即冻结账单快照与两侧语句，执行者凭租约领取，中断恢复沿用同份冻结依据，证据与终态原子落库。')
  +`<div class="panel"><div class="actions" style="margin-top:0;margin-bottom:20px"><button id="refresh">刷新队列</button><a href="#review">新建复核 →</a><span class="muted">${rows.length} 个批次</span></div>`
  +table(['编号 / 批次','基准样本','提交时间','运行状态','冻结依据','执行者租约','执行证据'],
    rows.map(x=>['<span class="mono">#'+x.id+'</span><br>'+esc(x.name),'#'+x.sample_id,esc(x.created_at),badge(x.status),
      freezeCell(x),leaseCell(x),
      ['passed','different','failed'].includes(x.status)?`<a href="#evidence/${x.id}">打开证据 →</a>`:'后台处理中，请刷新']))
  +'</div>';
  el.querySelector('#refresh').onclick=()=>historyPage(el);
}
