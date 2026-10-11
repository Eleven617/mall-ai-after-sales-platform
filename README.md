# Mall AI 售后平台

基于真实商城业务的智能售后系统，连接自然语言对话、订单调查、政策检索和用户确认后的业务执行。客户只需在一个对话框描述需求，系统根据问题选择直接解答或多步 Agent 处理，在同一会话展示调查进度和处理方案。

## 功能

- **统一客服对话**：问候、政策咨询、单项查询使用客服链路；复杂调查、方案比较和新的售后办理自动进入任务流程，无需客户选择 Agent 或填写任务表单。
- **多轮事项处理**：缺少信息时追问，客户直接在对话中补充；服务端关联当前账号、当前会话的处理事项。咨询其他问题后仍可查看原事项。
- **可确认的售后方案**：展示依据、预期效果和方案版本；支持修改售后类型、确认提交和暂不提交。Java 提交时重新校验身份、归属、资格和状态，保证重复确认不会重复写入。
- **订单与政策联合调查**：订单、物流和售后资格来自 Java 接口；政策问答通过版本化知识检索和证据核验形成回答。
- **随时转人工**：客户可直接说“转人工”或点击常驻入口，选择当前事项或一般咨询；查看交接卡并确认后登记案件。无需先提供订单，按钮路径不依赖模型。
- **人工售后闭环**：客户查看排队、处理和补件进度；处理人员领取、核验、请求补充、解决与结案。交接后原事项停止自动写入，避免人工与 Agent 重复操作。
- **问题分析与改进**：后台根据结构化交接信息异步分析原因，人工可复核分类；运营按统一时间窗口、业务、来源和原因筛选案例与统计，把问题分派为可追踪、需验证才能关闭的改进事项。

## 技术设计

### 对话驱动的 Agent 编排

FastAPI 统一入口通过结构化模型决策选择客服回答、创建事项、继续事项、请求澄清或人工交接。任务引用只从服务端读取的当前会话事项中选择；客户在同一对话中查看进度和确认方案。

TaskRuntime 管理计划、Skill 调用、事实产物、暂停恢复和版本化 ActionProposal。Executor 负责受控执行，Context Curator 管理上下文，Resolution Critic 提供方案检查。JSON Schema、工具白名单和参数校验约束模型输出。

### 业务执行与一致性

Java Spring Boot 是业务事实和最终写入的权威。Python 通过 API 获取事实，确认卡绑定方案引用和版本，提交经过资格重校验、幂等与事务处理。MySQL 保存业务数据，Outbox 与 RabbitMQ 支持异步业务流；Redis 提供会话、锁与短期状态，MongoDB 保存 Runtime 任务数据。

### 政策 RAG 与模型接入

版本化政策知识支持 Dense / Hybrid / Rerank 检索，回答经过来源、适用性与证据核验。DeepSeek 通过统一模型网关接入，结构化输出、调用预算和 Ledger 对账用于控制模型调用；证据不足时请求补充信息或拒绝推断。

### 人工交接与可追溯分析

交接复用 ActionProposal 的身份、版本、有效期和内容哈希校验。Java 使用稳定请求键与活动事项锁，在同一事务中关联案件、审计和 Outbox；提交结果不明时按原请求查询。客户、处理人员和运营使用独立身份与权限。

原因分析读取业务类别、客户选择、任务阶段与进度计数，不复制原始聊天。后台通过持久化待分析状态、领取租约和条件更新恢复任务；模型初判与人工结论分别留存，并记录输入哈希及分析版本。运营列表、总数与原因分布共享过滤条件；保留期管理提供预览、保留标记、分批清理和审计。

### 前端与工程

Vue + TypeScript + Vite 展示公开 DTO，将客服对话、处理进度和确认卡放在同一客户页面。Docker Compose 组织本地服务；pytest、JUnit、合同回放、现场验收与 GitHub Actions 覆盖不同层面的工程验证。

## 本地运行

安装 Docker Desktop，准备自己的 DeepSeek Key，并按本地配置说明注入：

```powershell
git clone https://github.com/Eleven617/mall-ai-after-sales-platform.git
Set-Location .\mall-ai-after-sales-platform
.\scripts\Prepare-PublicDemo.ps1
```

日常真实模型对话配置见 [本地对话说明](docs/LOCAL_CHAT.md)。启动后访问 <http://127.0.0.1:5173>；API 文档位于 <http://127.0.0.1:8000/docs>。密钥和临时账号密码不进入 Git。

## 代码导航

| 目录 | 职责 |
| --- | --- |
| `mall-ai-service/app/services/conversation_entry.py` | 统一对话路由与事项关联 |
| `mall-ai-service/app/runtime/` | 任务状态机、Skill、方案与确认 |
| `mall-ai-service/app/services/` | 客服编排、RAG、模型网关和质量工具 |
| `mall2/mall-portal/`、`mall2/mall-admin/` | 商城业务、权限、事务和人工协同 |
| `mall-ai-web/src/` | 客户对话及角色工作台 |
| `mall-ai-service/evals/`、`mall-ai-service/scripts/` | 评测合同与验证入口 |

## 验证与进一步阅读

统一入口实现与本轮真实模型回归记录在 [统一对话变更记录](docs/evidence/unified-conversation-entry.md)。既有版本的结果见 [测试与演示证据](docs/TEST_AND_DEMO_EVIDENCE.md) 和 [评测演进记录](docs/evidence/evaluation-evolution.md)，保留各自的版本与范围。

新版人工交接、人工处理与运营改进的实现和验收见 [人工交接升级记录](docs/HANDOFF_UPGRADE_IMPLEMENTATION.md)。

- [架构与责任边界](docs/architecture.md)
- [贡献与本地验证](CONTRIBUTING.md)
- [安全问题](SECURITY.md)
- [上游归属](UPSTREAM.md)

## 许可

本项目按 Apache-2.0 发布；上游商城代码及许可说明见 [NOTICE](NOTICE) 与 [UPSTREAM.md](UPSTREAM.md)。
