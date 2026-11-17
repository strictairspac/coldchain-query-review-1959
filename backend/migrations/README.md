# Schema 版本

## v2（冻结依据 + 执行者租约）

`src/config/schema.py` 的 `ensure_schema()` 在启动与 seed 时执行：

1. `Base.metadata.create_all` 建立新表（users/samples/batches/evidence/audit）。
2. 对已存在的 v1 库按 `information_schema.columns` 幂等补列，不删数据：
   - `batches.snapshot_table / frozen_original_sql / frozen_candidate_sql /
     snapshot_row_count / snapshot_checksum / frozen_at`：受理时冻结的账单快照与两侧语句。
   - `batches.lease_owner / lease_token / lease_until / attempts`：执行者租约与领取次数。
3. 每个受理批次另建独立快照表 `invoices_snapshot_<batch_id>`（`CREATE TABLE ... LIKE invoices
   INCLUDING DEFAULTS INCLUDING INDEXES` 后整表复制），并 `GRANT SELECT` 给 NOLOGIN
   `query_reader`。快照无原表约束/序列，冻结期间 invoices 仍可正常写账。
4. v1 旧批次/旧证据的冻结列为 NULL，API 以 `freeze_basis=null` 返回，照常可读。

## v1

SQLAlchemy metadata creates users/samples/batches/evidence/audit. seed_demo initializes the
separate invoices fixture table and NOLOGIN query_reader. invoices is the only permitted SQL
source. Run `python -m scripts.seed_demo` for repeatable initialization; natural keys preserve
user edits.
