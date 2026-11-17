# gb-4101 验证脚本与日志

本目录不属于应用源码，按 README 约定存放批次工作脚本与验证记录。脚本用标准库 + psycopg2 编写，
通过运行中的后端 HTTP API、真实 PostgreSQL 与真实 worker 进程验证，不模拟数据库行为。

## 前置（本机无 root/docker 时的用户态环境）

- micromamba 安装 PostgreSQL 16（端口 17740）与 Redis（端口 16379）。
- Python 3.11 虚拟环境安装 `backend/requirements.txt`。
- 启动后端：`SEED_DEMO=true python -m uvicorn src.main:app --port 19240`。
- e2e 与 crash 脚本自行启停 worker；运行前不要常驻 worker。

## 脚本与需求对应

| 脚本 | 验证的需求 |
|---|---|
| `e2e_freeze.py`（36 项断言，7 组） | 受理即冻结（快照表/冻结语句/校验和/GRANT）、比较中改账不影响结果、中断恢复同份依据且证据唯一、并发领取与过期执行者不能覆盖、冻结失败整批不受理、只读权限/422/429/403 限额与原比较口径、旧证据可读 |
| `stress_claim.py`（12 线程） | 同一批次并发领取仅 1 人成功、仅 1 次发布、证据唯一、attempts=1 |
| `crash_recovery.py`（真实 SIGKILL） | worker 在 compare 执行中被强杀后，新 worker 待租约过期重新领取，用同份冻结快照完成，attempts=2、证据唯一 |
| `static_server.js` | 等价 nginx.conf 的本地静态服务器（SPA fallback + `/api/` 去前缀代理），用于前端页面联调 |

`WORKER_DELAY_SECONDS` 是 worker 内置的测试钩子（默认 0 关闭），仅为 SIGKILL 演练提供可杀窗口。

## 最近一次结果

见 `verification.log`（36/36 e2e、并发压力、真实崩溃恢复全部通过）。
