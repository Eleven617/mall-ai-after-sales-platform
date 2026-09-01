# LangGraph 最小实验：订单异常诊断与人工确认

这是一个独立学习实验，不接入 FastAPI、Java、Redis、LLM 或真实订单数据，不能作为
商城项目已经上线的功能。

它只验证 LangGraph 的五个核心概念：

```text
State      订单异常处理过程中的共享状态
Node       一步确定性的业务处理
Edge       固定的状态流转
Conditional Edge  根据状态选择下一条边
Interrupt  在人工确认点暂停，之后以同一 thread_id 恢复
```

## 场景

用户反馈“订单迟迟未到”。图会执行：

```text
查演示订单
  -> 查演示物流
  -> 若物流异常，读取演示政策
  -> 生成“人工交接草稿”建议
  -> interrupt 暂停，等待确认
  -> Command(resume=...) 恢复并给出最终状态
```

订单不存在时，图直接结束；物流正常时，也不会进入人工确认节点。这展示了条件边。

## 运行

从 `mall-ai-service` 目录执行：

```powershell
.\labs\.langgraph-venv\Scripts\python.exe .\labs\langgraph_order_exception\order_exception_graph.py
.\labs\.langgraph-venv\Scripts\python.exe -m unittest discover -s .\labs\langgraph_order_exception -p "test_*.py" -v
```

## 与主项目的关系

当前商城的售后写入仍使用服务端确定性状态机；本实验不会替换它。

如果未来的“订单异常诊断 Agent”出现多分支、暂停恢复、人工接管和重试回退需求，本实验
验证的图模型才可能迁入主项目。届时还必须补上 Java 权限、Redis 持久化、真实工具、评测和
故障处理，不能直接复制本实验代码。

## 第二部分：LangGraph 中的受控 Agent 节点

`langgraph_agent_loop.py` 展示混合模式：模型只返回允许的下一步动作，LangGraph 负责
保存状态、执行受限节点、限制最大决策次数，并在人工确认点暂停。测试使用脚本化模型，
因此不消耗 API 额度；文件也包含一个可选的 DeepSeek JSON 决策适配器，但不会自动调用。

```powershell
.\labs\.langgraph-venv\Scripts\python.exe .\labs\langgraph_order_exception\langgraph_agent_loop.py
.\labs\.langgraph-venv\Scripts\python.exe -m unittest discover -s .\labs\langgraph_order_exception -p "test_langgraph_agent_loop.py" -v
```

## DeepSeek 真实决策演示

默认命令仍使用脚本模型，不消耗额度。下面这条命令才会读取项目根目录已有的
`DEEPSEEK_*` 配置，并让 DeepSeek 在每一步根据当前 State 选择一个允许的动作：

```powershell
$env:LANGGRAPH_LIVE_DEMO = "1"
.\labs\.langgraph-venv\Scripts\python.exe .\labs\langgraph_order_exception\langgraph_agent_loop.py
```

演示只使用假订单数据，不会访问 Java 商城、创建售后单或暴露密钥。真实模型输出仍要经过
JSON 模式、Pydantic 动作白名单、节点前置条件和最大决策步数限制。
