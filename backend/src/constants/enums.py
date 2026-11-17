ROLES=('admin','operator','viewer')
STATUSES=('queued','running','passed','different','failed')
# 批次状态机：待执行(queued) → 执行中(running) → 完成(passed/different)或失败(failed)
TERMINAL_STATUSES=('passed','different','failed')
# 执行者租约秒数：只有持有有效租约的执行者能发布结果；崩溃后租约到期可被重新领取
LEASE_SECONDS=30
# 冻结快照表名（batch_id 为正整数，标识符天然安全）
SNAPSHOT_TABLE=lambda batch_id:f'invoices_snapshot_{int(batch_id)}'
