"""请求内能力子图：业务载荷留在闭包，LangGraph 只接收执行序号。"""
from typing import TypedDict
from langgraph.graph import StateGraph
from langsmith import tracing_context


class CapabilityCursor(TypedDict):
    sequence: int


class RequestLocalGraph:
    """保留既有节点业务合同，不把凭证或 RAG 原文当成图 State。"""
    def __init__(self, payload_schema):
        self.nodes, self.edges, self.branches = {}, [], []

    def add_node(self, name, handler):
        self.nodes[name] = handler

    def add_edge(self, start, end):
        self.edges.append((start, end))

    def add_conditional_edges(self, start, router, paths):
        self.branches.append((start, router, paths))

    def compile(self):
        return self

    def invoke(self, payload):
        local = dict(payload)
        builder = StateGraph(CapabilityCursor)
        for name, handler in self.nodes.items():
            def node(state, handler=handler):
                local.update(handler(local))
                return {"sequence": state["sequence"]+1}
            builder.add_node(name, node)
        for start, end in self.edges:
            builder.add_edge(start, end)
        for start, router, paths in self.branches:
            def route(state, router=router):
                return router(local)
            builder.add_conditional_edges(start, route, paths)
        graph = builder.compile(name="CapabilitySubgraph")
        with tracing_context(enabled=False):
            graph.invoke({"sequence": 0}, {"callbacks": [], "recursion_limit": 80})
        return local
