# Final Agent Quality Baseline

> 当前权威快照：2026-09-12（Asia/Shanghai）。运行时代码提交：`52d5482455e2389cfd6c2ef15d233712607ffa9f`。本文件记录真实执行结果，不把旧报告或确定性合同扩大为生产能力。

## 运行边界

- Provider：DeepSeek `deepseek-chat`，`DeepSeekRuntimeProvider`。
- 输入：版本化合成 EvalCase；工具网关为 `synthetic_read_only_gateway`，不连接真实客户订单，不执行真实业务写入。
- Prompt：`agent_runtime_v3_3`；Skill Catalog：`skill_catalog_v3_0`。
- 运行数据、密码、Token、原始客户消息、完整订单号和原始工具载荷均未写入仓库或公开报告。

## Live model synthetic

| 套件 | 唯一 Case | 每 Case 次数 | 执行 | passed | failed | environment_blocked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 24 | 3 | 72 | **72** | 0 | 0 |
| holdout | 12 | 3 | 36 | **36** | 0 | 0 |

主集报告：`mall-ai-service/tmp/final-agent-quality-main-final5-20260912.json`，SHA-256 `b4041b3541e125b48e4b1114ff1e100aeeb6c40bea29f426d048850414be87d2`，suite SHA-256 `ef6c0ad66556eb03127e85ee6607a5cdf79bb8f69ddfa8749ecc29e913e97d53`。

Holdout 报告：`mall-ai-service/tmp/final-agent-quality-holdout-final4-20260912.json`，SHA-256 `822775b454e921dc50817f764783ddd14fc65910e267b27aa2e559ecc5869612`，suite SHA-256 `1a82b6bcaa9ce246590b3f10ef08897bea07f81af675c128f9b96542acb10e90`。

两套报告均为 `taskSuccess`、`clarificationCorrect`、`requiredSkillOrFactCoverage`、`proposalOrResumeSuccess` 全部通过；`irrelevantCalls=0`、`forbiddenSideEffects=0`、`duplicateFinalBusinessWrites=0`。主集调用 173 次模型决策、96 次工具调用、89 次 Context 调用；LLM 总调用 259，成功 259，Token `558431`，运行时延迟 p50/p95/max 为 `6297/10672/13406 ms`。Holdout 调用 88 次模型决策、42 次工具调用、42 次 Context 调用；LLM 总调用 130，成功 130，Token `280390`，运行时延迟 p50/p95/max 为 `5891/9422/9546 ms`。价格未配置，成本为 `unavailable`。

这些结果证明当前版本在合成只读网关和固定 Case 上的编排合同；不能证明所有自然语言、生产流量、真实用户或外部履约系统的准确率。

## Grounding

命令：`mall-ai-service/.venv/Scripts/python.exe scripts/evaluate_rag_grounding.py`，退出码 `0`。报告：`mall-ai-service/tmp/final-grounding-20260912.txt`，SHA-256 `fb90a00cdb4b835270126600190eb175ae13583db97b678080452c8be252d715`。

结果：15/15 Case、57/57 检查通过，`failed=0`，`environment_blocked=0`，未出现未批准证据源。报告中的人工 review marker 汇总为 13/15，属于人工复核提示，不改变硬比较器的 15/15 结果。

## 确定性与现场交叉证据

- FastAPI：`python -m pytest -q` → **362 passed**、1 条第三方弃用警告、7 个子断言，退出码 0。
- v3 manifest：**478/478** deterministic；preflight 代表性 Runtime **8/8**，退出码均为 0。它们是合同门，不是 478 条真实用户任务。
- Java portal 定向：**12/12**；Java admin 定向：**6/6**；Spring `MallPortalApplicationTests.contextLoads` 使用临时本地 Compose MySQL 配置 **1/1**。这不是完整 Mongo/Rabbit 生产集成。
- Vue：`npm run build` 通过，Vite 产物 JS 171.94 kB、CSS 40.03 kB。
- Compose：主栈和隔离 fault 栈均通过 `docker compose config --quiet`，各 8/8 服务 healthy；Engine `29.7.2`。
- 现场 Runner：报告 `tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`，SHA-256 `a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`，Fixture SHA-256 `d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`，`testedCodeCommit=52d5482`；browser 24/24、Java/MySQL 30/30、fault 36/36、durable recovery 32/32，合计 **122/122 passed、0 failed、0 environment_blocked**。
- 证据提交 `efd3dcdd5d9c628a98b697ad63b57fe78b932cd9` 的 GitHub Actions 已成功：[`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032)、[`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115)。

## 不可扩大结论

没有真实支付、仓储、物流、维修适配器；未宣称生产 SLA、生产 QPS、真实用户准确率、模型成本或真实外部履约成功。旧提交上的失败/阻断报告仍保留在 `tmp/` 或历史文档中，并按 Commit 不一致标为 stale/superseded，不与本快照相加。
