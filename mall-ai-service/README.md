# mall-ai-service

面向电商订单异常与售后处置的 FastAPI AI 服务。项目将自然语言问题路由到普通对话、RAG、受控业务工具或 Agent；订单和物流查询不直接访问数据库，而是携带用户 Bearer Token 调用 Java mall 服务，由 Java 服务完成 JWT 校验和订单归属校验。

## 当前能力

- <code>GET /health</code>：健康检查。
- <code>POST /chat</code>、<code>POST /chat/stream</code>：DeepSeek 普通对话和 SSE 输出。
- <code>POST /intent</code>：基于结构化 JSON 输出的客服意图识别。
- <code>POST /customer-service</code>：统一客服入口，支持缺少订单编号时的多轮追问与售后草稿续接。
  - RAG：Markdown 标题路径切分、项目内本地中文 Embedding、ChromaDB 向量检索、服务端证据元数据、低置信拒答和检索评测；客户接口只返回答案。
- 订单/物流工具：调用 Java 的受授权订单摘要接口，不向模型暴露收货地址、手机号或用户 ID。
- 售后异常主闭环：订单/商品/原因分轮收集，真实订单校验，RAG 政策证据，待确认方案与一次性提交。
- Agent：原生 Function Calling、只读工具白名单、步骤/超时/重复调用限制和脱敏追踪。

## 订单工具的安全边界

用户请求的订单编号是 <code>order_sn</code>，不是数据库内部订单 ID。调用链如下：

~~~text
浏览器 Bearer Token
    -> FastAPI customer-service
    -> mall_client 原样转发 Token
    -> Java /order/ai/detail/by-sn/{orderSn}
    -> Java 校验 JWT + 当前用户订单归属
    -> 返回最小订单摘要给 AI 服务
~~~

Java 返回的 AI 订单摘要仅包含订单编号、状态、物流公司、物流单号和商品名称。AI 服务不会接收或生成用户 ID，也不能直接执行退款、建单等写操作。

## 售后异常主闭环

写操作不是由模型的一句“提交”直接触发，而是由服务端状态机控制：

~~~text
用户自然语言申请退货
    -> FastAPI 收集订单号、商品和原因（可跨多轮）
    -> Java 用当前 Bearer Token 校验订单归属，返回最小订单摘要
    -> RAG 找到可引用的售后政策；无证据则转人工
    -> FastAPI 保存待确认方案（不暴露内部 order_item_id）
    -> 用户明确回复“确认”
    -> Java /returnApply/ai/create 再校验用户、订单、商品、状态和重复申请
~~~

模型只可提取用户描述中的商品提示和退货原因；它不能决定订单归属、商品内部
ID、价格、是否可退，或绕过确认直接提交。

## 环境变量

复制 <code>.env.example</code> 为 <code>.env</code>，填入模型密钥。不要提交 <code>.env</code>。

<code>MALL_API_BASE_URL</code> 默认指向本地 <code>mall-portal</code> 的 <code>http://127.0.0.1:8085</code>。

## Run

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\start.ps1
~~~

打开：

~~~text
http://127.0.0.1:8000/docs
~~~

## Docker Compose Demo

The repository root contains the reproducible local demonstration entrypoint:

~~~powershell
cd ..
.\scripts\Prepare-PublicDemo.ps1
~~~

The first run creates a local virtual environment if needed, downloads the
reviewed local BGE embedding model, builds the Chroma policy index from the
committed Markdown corpus, asks for your own optional DeepSeek key, and starts
the Java dependencies, FastAPI and Vue production bundle. Model weights and
the generated index are intentionally excluded from Git and Docker image
layers; Compose mounts them from the local project directory. Read the root
<code>README.md</code> and
<code>docs/BUILD_12_DELIVERY_AND_DEMO.md</code> before running it. Model keys
remain in <code>mall-ai-service/.env</code>; they are not copied into Docker
images. Local embedding and Chroma retrieval do not need a VPN; only live
DeepSeek calls require a reachable API endpoint.

## 测试

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

当前测试覆盖：

- 缺少订单编号后的多轮补参；
- 多个订单号/手机号等歧义输入时的安全澄清；
- Bearer Token 从 FastAPI 路由传入工具上下文；
- Java 订单摘要响应的字段最小化；
- 缺少或失效登录令牌时的安全错误返回。
- 售后草稿的订单/商品/原因分轮收集、多商品选择、无政策证据转人工、登录用户变更拒绝、确认单次消费；
- Agent 写工具阻止、重复调用停止、模型不可用降级，以及只保留白名单追踪字段。

这些是离线确定性单元测试，不等同于真实 Java、Redis、模型、向量库或浏览器
联调。验收清单见 <code>evals/order_exception_cases.json</code>；其中
<code>manual_live</code> 用例仍待部署联调时执行。

## 会话与 RAG 运行配置

- 本地学习默认使用内存会话存储；部署时设置
  `CONVERSATION_STORE_BACKEND=redis` 与 `REDIS_URL`，会话、待补参工具和待确认
  售后方案将持久化到 Redis。
- 长对话只保留最近消息；更早消息会压缩成摘要，订单号、SKU、退货原因和确认状态
  仍以结构化会话事实保存。
- RAG 内部结果保留文档名、标题路径、chunk ID 和距离供服务端核验；客户接口不返回这些字段。
  当全部结果超过 `RAG_MAX_DISTANCE` 时，服务拒绝确认而不是编造政策。
  - 正式演示使用项目内的 `BAAI/bge-small-zh-v1.5` ONNX 模型。向量化和 Chroma
    检索不需要 VPN 或云端 Embedding 密钥；DeepSeek 的证据核验和回答生成仍需正常网络。
    更换本地模型必须重建索引并重新运行评测，不能沿用旧距离阈值。
- 检索评测运行：

~~~powershell
.\.venv\Scripts\python.exe scripts\evaluate_rag.py
~~~
