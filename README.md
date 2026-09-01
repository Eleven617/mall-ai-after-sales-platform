# Mall 可信 AI 售后与 AgentOps 平台

这是一个本地可运行的电商售后演示系统。它将 Java 商城交易底座、FastAPI AI 编排服务、Vue 工作台、MySQL、Redis、RabbitMQ 与 MongoDB 组合为一个受控的 AI 售后闭环。

它不是生产 SaaS，也不宣称真实模型在所有输入上的准确率、线上 SLA 或真实支付/仓储/维修系统接入。

## 产品能力

- 统一售后 Agent：政策咨询、资格核验、新建申请、列表、状态、取消、修改与跟进。
- 政策 RAG：本地 embedding 与向量检索只提供政策证据；订单、物流、资格、申请状态始终由 Java 权威接口查询。
- 受控写入：模型只输出受限结构化意图和字段线索；创建、取消、修改均经 Redis 绑定的待确认动作，再由 Java 复核归属、状态和幂等。
- 可靠异步：售后与人工案件动作和 Outbox 在同一 MySQL 事务内；RabbitMQ 发布、重复消费和失败队列均有受控处理。
- 三种职责角色：客户统一售后、运营只读分析、开发者质量评测；另有独立的人工售后处理人员领取和处置复杂案件。
- AgentOps：版本化 Skill Catalog、脱敏 Trace、合成 EvalCase、确定性合同比较、人工审批的反馈候选和只读 MCP。
- 人工协同：复杂案件可规则入队、领取、请求补件、核验、处理、结案；客户只能查看自己的公开状态和允许补充的信息。

## 不可突破的边界

```text
Vue 浏览器
  -> FastAPI：受控编排、公开 DTO、会话/待确认状态
  -> Java：JWT、归属、资格、状态机、幂等、事务与最终写入
  -> MySQL / Outbox / RabbitMQ：可靠状态变化与异步事件
```

- FastAPI 不直接连接商城业务数据库，LLM 不拥有写库、退款或任意工具权限。
- RAG 不能替代订单事实，模型不能把“结构正确”当作“事实正确”。
- 客户、运营、质量开发者、人工售后处理人员使用不同身份与最小数据投影。
- 客户页面不返回 Token、内部 intent、工具原文、RAG chunk/距离、内部备注、队列、处理人员、完整 Trace 或其他用户数据。
- 模型、JSON 契约、Java/RAG/Redis/RabbitMQ 依赖不可用时，流程安全停止或显示待处理；不会凭猜测写业务数据。

## 仓库目录

| 目录 | 责任 |
| --- | --- |
| `mall2/` | Spring Boot 商城、JWT、MyBatis、事务、Outbox、RabbitMQ、人工协同状态机 |
| `mall-ai-service/` | FastAPI、LangGraph、RAG、Skill/Trace/Eval/MCP、公开 API 投影 |
| `mall-ai-web/` | 客户、运营、质量与人工处理人员的 Vue 页面 |
| `docker-compose.yml` | 本地完整演示环境 |
| `docs/` | 架构决策、交付与验收证据 |

## 从干净克隆启动

前置条件：Docker Desktop 已启动；首次准备本地 BGE Embedding 时需要正常网络下载公开模型。需要真实 DeepSeek 调用时，网络可直连 DeepSeek。政策切分、本地 BGE embedding、Dense/BM25/RRF/Rerank 实验均不依赖 VPN。

```powershell
# 如果还没有克隆：
# git clone https://github.com/Eleven617/mall-ai-after-sales-platform.git mall-ai-after-sales-platform
# Set-Location .\mall-ai-after-sales-platform
# 以下命令均从仓库根目录执行
.\scripts\Prepare-PublicDemo.ps1
```

该脚本会在本机创建被 Git 忽略的 `.env`、提示你输入自己的 DeepSeek Key、下载本地 Embedding、从已提交的政策 Markdown 构建 Chroma 索引，并启动 Docker Compose。它不会打印或提交 Key、Token、密码、模型权重或索引。

后续已有本地 RAG 资产时可直接启动：

```powershell
.\scripts\start-demo.ps1
```

如果只想验证确定性代码和 Compose 合同，不输入模型 Key，也可以：

```powershell
.\scripts\Prepare-PublicDemo.ps1 -SkipLiveModel
```

此模式的模型请求会安全停止，适合本地结构与权限验证；不是完整客服对话演示。

启动后：

- 客户/运营/质量/人工处理人员工作台：<http://127.0.0.1:5173>
- FastAPI 文档：<http://127.0.0.1:8000/docs>
- Java portal：<http://127.0.0.1:8085>

不要提交 `.env`、浏览器令牌、日志、Chroma 索引或 Docker 命名卷。停止本地环境时保留卷：

```powershell
.\scripts\stop-demo.ps1
```

不要把 `docker compose down -v` 用于需要保留演示数据的环境。

该项目的发布镜像不内置本地模型权重和 Chroma 索引；它们由显式准备脚本在本机生成并通过 Compose 挂载。Dense 是默认检索；可选 Reranker 不会成为首次启动前置条件。

## 本地演示身份：由你自行设置密码

这是“下载后在自己电脑运行”的本地 Demo，不是向所有 GitHub 访客开放同一组线上测试账号。完整 AI 对话需要运行者自己的 DeepSeek Key；不配置 Key 时仍可启动结构和权限验证，但模型请求会安全停止。

仓库、文档和脚本不保存任何演示账号密码；此前自动验收用的是一次性随机账号，因此不能把它当成你应当记住的登录凭据。现在可用下面的本地初始化脚本，**在你的终端输入一次自己选择的密码**，由它只在本机 Compose 数据库中建立或重置最小权限演示身份：

```powershell
# 当前目录为仓库根目录
.\scripts\Initialize-LocalDemoAccess.ps1 -PrepareCustomerFixtures
```

它不会把密码打印、写入文件或加入 Git。运行者输入的这一份密码仅用于其自己的本机 Compose 数据库，并会设置下面五个固定用户名：

| 本地角色 | 用户名 |
| --- | --- |
| 客户 A / 客户 B | `localDemoCustomerA` / `localDemoCustomerB` |
| 运营人员 | `localDemoOperations` |
| AI 质量开发者 | `aiQualityDeveloper` |
| 人工售后处理人员 | `afterSalesProcessor` |

同一位运行者可用自己刚输入的密码登录这些本地演示身份；客户、运营、质量开发者和人工处理人员仍使用不同角色和接口边界。脚本提交后会在本机通过对应的 FastAPI 登录边界验证适用身份，但不会显示或保存返回的 Token。若只需检查脚本而不改任何账号，可运行：

```powershell
$password = Read-Host "Temporary dry-run password" -AsSecureString
.\scripts\Initialize-LocalDemoAccess.ps1 -DemoPassword $password -DryRun
```

## 验证命令

```powershell
# 以下命令均从仓库根目录执行
# FastAPI 全量回归
Push-Location .\mall-ai-service
.\.venv\Scripts\python.exe -m pytest -q
Pop-Location

# Vue 类型检查与生产构建
Push-Location .\mall-ai-web
npm run build
Pop-Location

# Java 人工协同 / Outbox 定向测试；Maven 根 POM 默认跳过测试，必须显式覆盖
Push-Location .\mall2
mvn -pl mall-portal -am "-Dtest=AiCaseHandoffServiceImplTest,AiServiceCaseServiceImplTest,AiServiceCaseOutboxPublisherTest,AiServiceCaseEventReceiverTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
mvn -pl mall-admin -am "-Dtest=AiServiceOperationsServiceImplTest,AiServiceOperationsControllerTest" "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
Pop-Location

# Compose 静态合同，不启动或删除容器
docker compose config --quiet
```

详细的可复核结论和当前未验证项见 [测试与演示证据](docs/TEST_AND_DEMO_EVIDENCE.md)。

## 架构、演示与公开边界

- [架构与责任边界](docs/architecture.md)
- [FR-01～FR-19 实施映射](docs/FINAL_UPGRADE_IMPLEMENTATION_RECORD.md)
- [13 步本地演示脚本](docs/demo-script.md)
- [评测、Profile 与安全回放](docs/evaluation.md)
- [隐私、数据可见性与非目标](docs/privacy-and-boundaries.md)
- [上游/二次开发/AI 辅助贡献矩阵](docs/CONTRIBUTION_MATRIX.md)
- [公开发布记录与验证边界](docs/PUBLIC_RELEASE_RECORD.md)
- [重大升级变更记录](docs/UPGRADE_CHANGELOG.md)
- [公开前人工检查清单](docs/PUBLIC_RELEASE_CHECKLIST.md)
- [贡献与本地验证](CONTRIBUTING.md)

## 安全与开源说明

- 报告安全问题请看 [SECURITY.md](SECURITY.md)。
- 本仓库按 [Apache-2.0](LICENSE) 发布；`mall2/` 源自 macrozheng/mall，完整归属和二次开发边界见 [UPSTREAM.md](UPSTREAM.md) 与 [NOTICE](NOTICE)。
- 面向人类和 AI 编程协作的工程规则见 [AGENTS.md](AGENTS.md)。
