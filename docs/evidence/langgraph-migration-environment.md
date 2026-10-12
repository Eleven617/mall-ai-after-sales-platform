# 统一图迁移：真实本机环境验收

日期：2026-10-12。用户恢复任务后明确授权启动/重建环境、专用合成数据经 Java 写入和重启对账；没有授权或执行付费模型调用。

状态：`LOCAL_MIGRATION_VALIDATED`。完成统一图代码迁移及本机无外部模型验收，不等同于远程发布或模型质量评测。执行工作区尚未提交，基线 HEAD 为 `60d53bd1fad3af444fd017f14035961427cca2c9`；源码 SHA-256 为 `01ae7bcbe682ceac475844505761d26406818be5450c03f67533877d7b651f64`。

## 当前结果

| 验证 | 结果与边界 |
|---|---|
| FastAPI 全量 | 562 cases + 16 subtests，578/578；0 failed/skipped |
| 真实 Mongo/Redis | 准备 3 项、重启后 9 项通过；独立验收库；实际 AI 容器重启 |
| Java 响应丢失 | 真实提交成功后在网关抛出合成 TimeoutError，Mongo 保留 unknown；重启 AI 按原 key 查回，申请数仍为 1 |
| 售后主链 | Proposal 修改、旧版本 409、Java 资格重校验、确认写入、回查、重复确认 0 写入、跨账号隔离通过 |
| 暂停恢复 | 真实 AI 重启后继续同一任务；读取 Java 事实，业务写入 0 |
| 浏览器 | 主链/恢复链 8 张业务帧，客户/运营/处理人员页面通过 |
| 会话与子图 | 8 项通过：多任务选择、请求去重、政策子图、插问、继续、未选任务不动、Java 查询、旧确认拒绝 |
| 人工交接与运营 | 30 项 HTTP/浏览器/重启检查通过；含撤回不写、并发确认、领取、审阅、处理到结案、问题改进闭环、运营子图读取实际 Java 聚合 |
| Provider | API Key 在验收容器被显式置空，live auth=0，模型后台作业关闭；外部请求/Token 0/0 |

机器汇总为 [environment.json](langgraph-acceptance/environment.json)，28 个具名跨报告断言。它们是底层报告的可追踪汇总，不是额外 28 次独立业务场景。汇总保存原报告及验收脚本哈希，校验器要求全部必要能力齐全，不能靠空报告/少报项目通过。

政策检索读取本地真实索引；路由、证据判定和回答使用明确的脚本替身。运营分析读取 Java 实际授权聚合，草稿生成使用脚本替身。TaskGraph 使用 deterministic/scripted Provider。这些结果验证框架迁移、边界和数据流，**不验证 DeepSeek 的语义质量**。

## 数据与切换

切换前只读聚合旧任务共 1,890 条：waiting_for_user 414、ready_to_commit 27、completed 584、waiting_human 60、blocked 354、executing 451。该统计包含历史/过期记录，不能称为 1,890 个活跃任务；没有批量更新、删除或强行恢复它们。

保留旧 AI 镜像 `mall-ai-langgraph-rollback:20261012`，先停止旧 AI/Web，再以新镜像启动，Java/MySQL/Mongo/Redis/RabbitMQ 的卷和已有数据保留。容器标签 `dirty-langgraph-01ae7bcbe682` 明确是源码快照标识，不冒充 Git 提交。

新增合成客户通过 Java 注册并创建订单；验收专用运营/处理人员身份由既有隔离 fixture 初始化器创建，案件、审核、售后等业务变更全部经 Java API。临时密码和 Token 仅在进程内/子进程 stdin 传递，不进入证据。合成记录保留用于审计，未清库。

## 验收工具修正

本轮首次 Java 对账脚本因容器与宿主路径层级不同而在导入阶段停止，尚未执行业务请求；修复路径后执行成功。人工验收工具的新增断言首次把旧分类字段预期为 PENDING、把撤回预期为任务 cancelled；核对现有 Java/Runtime 合同后，分别校准为旧分类 UNAVAILABLE、撤回提案后任务 executing 且无行动卡/无案件。没有修改业务状态机来迎合测试。失败原报告仍保留在 tmp，最终报告独立归档。

## 未执行

没有付费模型评测、新 SHA 远程 CI、Git 提交/推送、生产上线或完整旧镜像回退演练。当前本机保持 deterministic 且模型后台作业关闭。不得把原有 live 评测、历史 122/122 或旧 main CI 绑定为本次迁移结果。

完整环境报告、受限脚本和回退约束见 [迁移手册](../architecture/LANGGRAPH_MIGRATION_RUNBOOK.md)。
