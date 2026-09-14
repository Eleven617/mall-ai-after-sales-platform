# Mall v3.0 Release Gate 复核

## 当前权威结论｜最终公开收口

运行时代码 `0162c4059c35211852f409a4c3517a87997b4f56`，分支 `codex/v3.0.1-offline-acceptance`。当前 Release Gate：**NOT_COMPLETE**。本冻结提交 FastAPI 回归为 376 passed、12 个子断言，v3 manifest/preflight 为 478/478、8/8；浏览器现场 24/24、Java/MySQL 30/30、故障注入 36/36 通过。唯一 v3.0.1 DeepSeek 候选批次在真实展示链路返回脱敏 ShowcaseError 后停止，主集、补充集、Grounding 未执行，Durable live 32 条 environment_blocked。

提交 `4d452d06f0f6e75d1b8d8d929dd40e5fa640b28a` 的远程 `mall-ci` 与 `quality-evaluation` 均实际 success：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821040162)、[`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34821040035)。候选批次报告位于 `tmp/deepseek-v3.0.1-candidate.json`（SHA-256 `1a6e0016fdc5116ea68690e14167f5351391cd75bd827abe613953196f7cd9d2`，本地忽略，不提交原始载荷）。唯一事实源：[`current-release-facts.json`](current-release-facts.json)；本轮结果：[`v3.0.1-offline-and-live-acceptance.md`](v3.0.1-offline-and-live-acceptance.md)。

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
