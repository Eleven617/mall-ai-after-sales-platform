# Mall v3.0 Release Gate 复核

## 当前权威结论｜最终公开收口

运行时代码 `9c7c29045c28446b16a609768cd4b4c1202f8a51`，分支 `main`。本地合成 Gate 已通过：FastAPI 365、DeepSeek main 72/72、supplemental 36/36、Grounding 15/15 和 57/57 checks、Java portal core 12/12 + compatibility 2/2、admin 6/6、Spring 1/1、Vue build、deterministic 478/478（代表性 8/8）、现场 122/122。补充集合不是独立盲测；deterministic 不是 E2E；所有现场数字仅适用于合成 Fixture 和本机 Docker 技术栈。

最终证据提交 `78c5c3c` 已得到两个远程 success：[`mall-ci`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34716325261) 与 [`quality-evaluation`](https://github.com/Eleven617/mall-ai-after-sales-platform/actions/runs/34716325231)。运行时代码仍绑定 `9c7c290`，本次只是文档/事实回填。唯一事实源：[`current-release-facts.json`](current-release-facts.json)；展示证据：[`final-showcase-evidence.md`](final-showcase-evidence.md)。

公开提交 `e0c8b36` 的首次 `mall-ci` 只在 OSV 步骤失败：扫描容器对 Java 本地 `1.0-SNAPSHOT` reactor 做传递解析时无法从远程仓库找到内部模块，退出码 127；gitleaks、Python、Java、Web、Compose 和 public-release 均通过。修复为 OSV `--no-resolve` 后仍扫描所有显式 Python/npm lockfile 与 `mall2` POM 的直接依赖，未关闭扫描、未使用 `continue-on-error`，待新提交远程复核。

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
