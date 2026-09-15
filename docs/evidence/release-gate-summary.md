# Mall v3.0 Release Gate 复核

## 当前权威结论｜v3.0.1 在线验收（2026-09-15）

代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`；离线 readiness 24/24 通过；FastAPI 382、deterministic 478/478、Java 14/14 + Spring 1/1、Vue build、当前本机合成现场 122/122 通过。唯一 DeepSeek candidate 在第一展示链失败，锁定 `FAILED`，Release Gate **NOT_COMPLETE**。共享 ledger 观察 9 次 Provider 请求、9 成功、0 失败、27,329 tokens；main/supplemental/Grounding 未执行。

正式候选报告 SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`；现场报告 SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`。本轮 GitHub push 因 443 超时，当前 SHA 的 Actions 尚未验证；旧 run 不替代。

## 当前权威结论｜最终公开收口

运行时代码 `54de463b4990229b591e1fd0a278f754bf240678`，分支 `codex/v3.0.1-offline-acceptance`。当前 Release Gate：**NOT_COMPLETE**。本冻结提交 FastAPI 回归为 **381 passed**、12 个子断言，v3 manifest/preflight 为 478/478、8/8；浏览器现场 24/24、Java/MySQL 30/30、故障注入 36/36、Durable 32/32 通过（各类 `environment_blocked=0`）。本轮不调用 DeepSeek；deterministic/replay 展示链通过，但不作为真实模型泛化证据。

提交 `5bfdc3c7c8eb88f76abecc6ea063eb2173880813` 的远程 `mall-ci` 与 `quality-evaluation` 均实际 success：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821813055)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821813117)。候选批次报告位于 `tmp/deepseek-v3.0.1-candidate.json`（SHA-256 `1a6e0016fdc5116ea68690e14167f5351391cd75bd827abe613953196f7cd9d2`，本地忽略，不提交原始载荷）。唯一事实源：[`current-release-facts.json`](current-release-facts.json)；本轮结果：[`v3.0.1-offline-and-live-acceptance.md`](v3.0.1-offline-and-live-acceptance.md)。

本轮证据提交 `bd3a5cf787f87e2819c73021fc9a356c6c65da85` 的远程门禁已真实通过：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831197)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34931831222)。

旧 releaseId `v3.0-deepseek-flash-final` 的锁保持不变；本轮新候选锁为 [`deepseek-release-lock-v3.0.1.json`](deepseek-release-lock-v3.0.1.json)，记录 `candidate-5f1d90208743` 失败和 0 provider requests，不允许无授权重跑。

历史 `e0c8b36` 的首次 `mall-ci` 曾因 OSV 容器无法解析 Java 本地 `1.0-SNAPSHOT` reactor 而失败（退出码 127）；后续工作流已改为 `--no-resolve` 并继续扫描显式 Python/npm lockfile 与 `mall2` POM 直接依赖。该过程属于历史 CI 审计，不代表当前 SHA 已远程通过；当前推送后必须以 GitHub 返回的最新结果为准。

## 历史审计记录（以下内容不代表当前 Commit）

## 当前权威结论（2026-09-12）

运行时代码提交：`52d5482455e2389cfd6c2ef15d233712607ffa9f`；证据推送提交：`efd3dcdd5d9c628a98b697ad63b57fe78b932cd9`；分支：`main`。工作区在本次运行开始时除 Git 忽略的 `tmp/` 外干净。本机合成 Release Gate：**通过**；证据提交对应的远程 Actions 也已通过：[`mall-ci` run 34646346032](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346032)、[`quality-evaluation` run 34646346115](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34646346115)。

## 门禁矩阵

| 门禁 | 结果 | 证据/范围 |
| --- | --- | --- |
| FastAPI 回归 | **362 passed / 0 failed** | `.venv/Scripts/python.exe -m pytest -q`，exit 0；1 条第三方弃用警告、7 子断言 |
| v3 deterministic | **478/478；代表性 8/8** | manifest/preflight，合同模式、无模型/无写入 |
| Live model main | **72/72** | 24 Case × 3，DeepSeek + synthetic read-only gateway |
| Live model holdout | **36/36** | 独立 12 Case × 3，非生产泛化率 |
| Grounding | **15/15；57/57 checks** | 当前 grounding runner，成本未配置 |
| Java | **portal 12/12；admin 6/6；Spring 1/1** | 显式 `-DskipTests=false`；Spring smoke 指向本地 Compose MySQL |
| Web | **passed** | `npm run build` |
| Docker/Compose | **8/8 + 8/8 healthy** | 主栈与隔离 fault 栈，Engine 29.7.2 |
| 现场 Runner | **122/122** | browser 24、Java/MySQL 30、fault 36、durable 32 |

## 报告指纹

- 现场报告：`tmp/field-acceptance-final/field-20260911T203212Z-95f5755e/field-acceptance.json`；SHA-256 `a0fbcd5c22638be8be480ae08344596a14d7874eafcd65194242b3f4df8c803e`。
- Fixture：`tmp/field-fixture.json`；SHA-256 `d4829bd272dad498b17890b24595c288150ed89d4f59b062424b70067513e093`。
- 主 live：`mall-ai-service/tmp/final-agent-quality-main-final5-20260912.json`；SHA-256 `b4041b3541e125b48e4b1114ff1e100aeeb6c40bea29f426d048850414be87d2`。
- Holdout：`mall-ai-service/tmp/final-agent-quality-holdout-final4-20260912.json`；SHA-256 `822775b454e921dc50817f764783ddd14fc65910e267b27aa2e559ecc5869612`。
- Grounding：`mall-ai-service/tmp/final-grounding-20260912.txt`；SHA-256 `fb90a00cdb4b835270126600190eb175ae13583db97b678080452c8be252d715`。

## 历史失败与处理

- 旧的 122 `environment_blocked` 报告是 Docker Desktop/Fixture 阻断，已被 Docker 恢复后的当前提交现场报告 superseded；不能与 122/122 相加。
- live main-final2/3/4 的 70/72、71/72 失败保留在 [最终失败矩阵](final-agent-failure-matrix.md)，当前通过来自通用 Runtime/Prompt 修复后的新报告，不是删除 Case 或放宽断言。
- Build 14A 退货状态资格拒绝被保留为真实 Java 资格负向边界；未伪造成功。

## 不能宣称

本 Gate 仅覆盖本机合成数据、DeepSeek 合成只读网关和本地 Docker 现场。没有真实支付、仓储、物流、维修系统；不能宣称生产 SLA/QPS、真实用户准确率、模型成本或线上部署。上游 `macrozheng/mall` 基础能力不归为个人原创。
# v3.0.1 最终在线验收门禁（2026-09-15）

**当前结论：NOT_COMPLETE。** 代码冻结 `06ef600e51e7b0dc362d43a98e274c28144738d8`；分支 `codex/v3.0.1-offline-acceptance`。离线就绪检查 24/24 通过，当前 SHA 的本机合成现场 122/122 通过，但唯一正式 DeepSeek 候选在第一条展示链失败，锁定为 `FAILED`，不得重试。

| Gate | 结果 | 证据 |
| --- | --- | --- |
| FastAPI | **382 passed / 0 failed** | `.venv/Scripts/python.exe -m pytest -q`，exit `0` |
| Java | portal **14/14**；Spring **1/1** | Maven `-DskipTests=false`，exit `0` |
| Web | **passed** | `npm run build`，exit `0` |
| Compose | **8/8 healthy** | `docker compose config --quiet`、健康状态 |
| v3 deterministic | **478/478；8/8** | manifest/preflight，无模型、无业务写入 |
| 现场 Runner | **122/122** | browser 24、Java/MySQL 30、fault 36、durable 32；合成数据 |
| DeepSeek candidate | **FAILED** | `candidate-226cdd440e85`；第一展示链失败，后续套件未执行 |
| GitHub Actions | **待当前 SHA 远程验证** | 本轮 GitHub 443 推送超时；旧 run 不并入 |

## DeepSeek 候选边界

正式报告：`tmp/deepseek-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，SHA-256 `6615d069122cb66ee8f3467f98ae79457ef287afd6f19c5e56035c45fb0b65c8`。Release lock：`docs/evidence/deepseek-release-lock-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json`，SHA-256 `f6efe1612697bec6ba55505d83acdd320c1db044dc89f4e276891e32517b2a36`。

候选报告在第一条 `main_open_task_closed_loop` 展示链停止；clarify/pause/resume、fact-change、main 24×3、supplemental 12×3 和 Grounding 均为 `not_executed`。共享跨进程账本观察到 9 个 Provider metadata events（9 成功、0 失败、27,329 tokens），但主机入口未设置 `MALL_RELEASE_LEDGER_PATH`，锁/报告自身记录为 0；两者差异按失败证据公开，绝不后处理为“通过”。这些请求不能推导任务准确率、成本或泛化能力。

## 当前现场证据

报告：`tmp/offline-field-acceptance/field-20260915T064300Z-99f3dc2f/field-acceptance.json`，SHA-256 `ec337708baa422fcd11bf2ac2334372e88f3592f4dde454ab0f674413704122b`，`testedCodeCommit=06ef600e51e7b0dc362d43a98e274c28144738d8`。就绪报告：`docs/evidence/v3.0.1-live-readiness.json`，SHA-256 `e559244e6c9a14689d15b44d4203070f4a6ed8fc9660ed2cbaaa24ab7b380614`。现场只使用合成账号、订单和政策；fault 组中本地安全停止/隔离 Compose 的合同场景不代表外部供应商宕机。

当前不生成 live GIF，也不更新 README 为“真实模型通过”。禁止宣称生产部署、真实用户自然语言准确率、生产 SLA、真实支付/仓储/物流/维修履约或真实模型成本。
