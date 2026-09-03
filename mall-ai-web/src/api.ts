import type {
  AgentTaskPublicView,
  AfterSalesApplicationView,
  CustomerFeedbackRequest,
  CustomerFeedbackReasonCode,
  CustomerFeedbackView,
  CustomerConversationDetail,
  CustomerConversationSummary,
  CustomerLoginRequest,
  CustomerLoginResponse,
  CustomerServiceRequest,
  CustomerServiceResponse,
  CustomerServiceCaseCancelRequest,
  CustomerServiceCaseInformationRequest,
  CustomerServiceCaseReopenRequest,
  CustomerServiceCaseTimelineEntry,
  CustomerServiceCaseView,
  EvaluationProfile,
  FeedbackCandidate,
  HandoffOverview,
  MemberProfile,
  OperationsAnalysisResponse,
  OperationsCase,
  OperatorLoginRequest,
  OperatorLoginResponse,
  OperatorProfile,
  QualityDeveloperLoginRequest,
  QualityDeveloperLoginResponse,
  QualityDeveloperProfile,
  QualityEvaluationMode,
  QualityEvaluationRun,
  QualityLocalMetric,
  QualityReplayStatus,
  ServiceProcessorActionRequest,
  ServiceProcessorCaseView,
  ServiceProcessorClaimRequest,
  ServiceProcessorLoginRequest,
  ServiceProcessorLoginResponse,
  ServiceProcessorProfile,
} from "./types";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export class CustomerServiceApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "CustomerServiceApiError";
  }
}

export async function sendCustomerMessage(
  request: CustomerServiceRequest,
  authorization?: string,
): Promise<CustomerServiceResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authorization) {
    headers.Authorization = authorization;
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/customer-service`, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
    });
  } catch {
    throw new CustomerServiceApiError(
      "无法连接 AI 服务。请确认 FastAPI 已启动，并检查 Vite 代理配置。",
    );
  }

  const rawBody = await response.text();
  let payload: unknown = null;
  try {
    payload = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    // Keep a generic client-safe error below; do not render arbitrary HTML.
  }

  if (!response.ok) {
    const detail = extractErrorDetail(payload);
    throw new CustomerServiceApiError(
      detail || `AI 服务请求失败（HTTP ${response.status}）。`,
      response.status,
    );
  }

  if (!isCustomerServiceResponse(payload)) {
    throw new CustomerServiceApiError("AI 服务返回的数据格式不符合客服接口约定。");
  }
  return payload;
}

export async function createAgentTask(
  request: { session_id: string; goal: string; success_criteria?: string[] },
  authorization: string,
): Promise<AgentTaskPublicView> {
  const response = await fetch(`${apiBaseUrl}/agent-tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: authorization },
    body: JSON.stringify(request),
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接 Agent Runtime 服务。", 503);
  });
  return parseAgentTaskResponse(response, "创建 Agent 任务失败");
}

export async function getAgentTasks(
  sessionId: string,
  authorization: string,
): Promise<AgentTaskPublicView[]> {
  const response = await fetch(
    `${apiBaseUrl}/agent-tasks?session_id=${encodeURIComponent(sessionId)}`,
    { method: "GET", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法读取 Agent 任务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `读取 Agent 任务失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isAgentTaskPublicView)) {
    throw new CustomerServiceApiError("Agent 任务返回的数据格式不符合公开接口约定。", 502);
  }
  return payload;
}

export async function continueAgentTask(
  taskRef: string,
  message: string,
  authorization: string,
): Promise<AgentTaskPublicView> {
  const response = await fetch(
    `${apiBaseUrl}/agent-tasks/${encodeURIComponent(taskRef)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify({ message }),
    },
  ).catch(() => {
    throw new CustomerServiceApiError("无法继续 Agent 任务。", 503);
  });
  return parseAgentTaskResponse(response, "继续 Agent 任务失败");
}

export async function confirmAgentTaskAction(
  taskRef: string,
  confirmation: "confirm" | "withdraw",
  authorization: string,
): Promise<AgentTaskPublicView> {
  const response = await fetch(
    `${apiBaseUrl}/agent-tasks/${encodeURIComponent(taskRef)}/action`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify({ confirmation }),
    },
  ).catch(() => {
    throw new CustomerServiceApiError("Agent 行动确认服务暂不可用。", 503);
  });
  return parseAgentTaskResponse(response, "Agent 行动确认失败");
}

export async function loginCustomer(
  request: CustomerLoginRequest,
): Promise<CustomerLoginResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new CustomerServiceApiError("无法连接登录服务，请确认 FastAPI 和 Java 商城已启动。", 503);
  }

  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `登录失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isCustomerLoginResponse(payload)) {
    throw new CustomerServiceApiError("登录服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCurrentMember(
  authorization: string,
): Promise<MemberProfile> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/auth/me`, {
      method: "GET",
      headers: { Authorization: authorization },
    });
  } catch {
    throw new CustomerServiceApiError("无法验证当前登录状态。", 503);
  }

  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `登录状态验证失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isMemberProfile(payload)) {
    throw new CustomerServiceApiError("登录服务返回的用户信息格式不符合约定。", 502);
  }
  return payload;
}

export async function getAfterSalesApplications(
  authorization: string,
): Promise<AfterSalesApplicationView[]> {
  const response = await fetch(`${apiBaseUrl}/customer-service/after-sales-applications`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接售后记录服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `售后记录查询失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isAfterSalesApplicationView)) {
    throw new CustomerServiceApiError("售后记录返回的数据格式不符合接口约定。", 502);
  }
  return payload;
}

export async function getCustomerServiceCases(
  authorization: string,
): Promise<CustomerServiceCaseView[]> {
  const response = await fetch(`${apiBaseUrl}/customer-service/service-cases`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接人工协同进度服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工协同进度读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isCustomerServiceCaseView)) {
    throw new CustomerServiceApiError("人工协同进度返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCustomerServiceCaseTimeline(
  caseId: string,
  authorization: string,
): Promise<CustomerServiceCaseTimelineEntry[]> {
  const response = await fetch(
    `${apiBaseUrl}/customer-service/service-cases/${encodeURIComponent(caseId)}/timeline`,
    { method: "GET", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接人工协同进度服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工协同进度读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isCustomerServiceCaseTimelineEntry)) {
    throw new CustomerServiceApiError("人工协同进度返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function submitCustomerServiceCaseInformation(
  caseId: string,
  request: CustomerServiceCaseInformationRequest,
  authorization: string,
): Promise<CustomerServiceCaseView> {
  return postCustomerServiceCaseAction(caseId, "customer-information", request, authorization);
}

export async function cancelCustomerServiceCase(
  caseId: string,
  request: CustomerServiceCaseCancelRequest,
  authorization: string,
): Promise<CustomerServiceCaseView> {
  return postCustomerServiceCaseAction(caseId, "cancel", request, authorization);
}

export async function reopenCustomerServiceCase(
  caseId: string,
  request: CustomerServiceCaseReopenRequest,
  authorization: string,
): Promise<CustomerServiceCaseView> {
  return postCustomerServiceCaseAction(caseId, "reopen", request, authorization);
}

export async function submitCustomerFeedback(
  request: CustomerFeedbackRequest,
  authorization: string,
): Promise<CustomerFeedbackView> {
  const response = await fetch(`${apiBaseUrl}/customer-service/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: authorization },
    body: JSON.stringify(request),
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接反馈服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `反馈提交失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isCustomerFeedbackView(payload)) {
    throw new CustomerServiceApiError("反馈服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

async function postCustomerServiceCaseAction(
  caseId: string,
  action: "customer-information" | "cancel" | "reopen",
  request:
    | CustomerServiceCaseInformationRequest
    | CustomerServiceCaseCancelRequest
    | CustomerServiceCaseReopenRequest,
  authorization: string,
): Promise<CustomerServiceCaseView> {
  const response = await fetch(
    `${apiBaseUrl}/customer-service/service-cases/${encodeURIComponent(caseId)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify(request),
    },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接人工协同服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工协同操作失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isCustomerServiceCaseView(payload)) {
    throw new CustomerServiceApiError("人工协同操作返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function createCustomerConversation(
  conversationId: string,
  authorization: string,
): Promise<CustomerConversationSummary> {
  const response = await fetch(
    `${apiBaseUrl}/customer-service/conversations/${encodeURIComponent(conversationId)}`,
    { method: "POST", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法创建新的历史会话。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `新建会话失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isCustomerConversationSummary(payload)) {
    throw new CustomerServiceApiError("历史会话服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCustomerConversations(
  authorization: string,
): Promise<CustomerConversationSummary[]> {
  const response = await fetch(`${apiBaseUrl}/customer-service/conversations`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法读取历史会话。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `历史会话读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isCustomerConversationSummary)) {
    throw new CustomerServiceApiError("历史会话服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCustomerConversation(
  conversationId: string,
  authorization: string,
): Promise<CustomerConversationDetail> {
  const response = await fetch(
    `${apiBaseUrl}/customer-service/conversations/${encodeURIComponent(conversationId)}`,
    { method: "GET", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法打开历史会话。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `历史会话打开失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isCustomerConversationDetail(payload)) {
    throw new CustomerServiceApiError("历史会话服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function deleteCustomerConversation(
  conversationId: string,
  authorization: string,
): Promise<void> {
  const response = await fetch(
    `${apiBaseUrl}/customer-service/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法删除历史会话。", 503);
  });
  if (response.status === 204) {
    return;
  }
  const payload = await parseJsonBody(response);
  throw new CustomerServiceApiError(
    extractErrorDetail(payload) || `历史会话删除失败（HTTP ${response.status}）。`,
    response.status,
  );
}

export async function loginServiceProcessor(
  request: ServiceProcessorLoginRequest,
): Promise<ServiceProcessorLoginResponse> {
  const response = await fetch(`${apiBaseUrl}/service-operations/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接人工处理人员登录服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工处理人员登录失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isServiceProcessorLoginResponse(payload)) {
    throw new CustomerServiceApiError("人工处理人员登录返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCurrentServiceProcessor(
  authorization: string,
): Promise<ServiceProcessorProfile> {
  const response = await fetch(`${apiBaseUrl}/service-operations/me`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法验证人工处理人员登录状态。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工处理人员身份验证失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isServiceProcessorProfile(payload)) {
    throw new CustomerServiceApiError("人工处理人员身份返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getServiceProcessorCases(
  authorization: string,
): Promise<ServiceProcessorCaseView[]> {
  const response = await fetch(`${apiBaseUrl}/service-operations/cases`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接人工处理案件服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工处理案件读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isServiceProcessorCaseView)) {
    throw new CustomerServiceApiError("人工处理案件返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function claimServiceProcessorCase(
  caseId: string,
  request: ServiceProcessorClaimRequest,
  authorization: string,
): Promise<ServiceProcessorCaseView> {
  return postServiceProcessorCase(caseId, "claim", request, authorization);
}

export async function actOnServiceProcessorCase(
  caseId: string,
  request: ServiceProcessorActionRequest,
  authorization: string,
): Promise<ServiceProcessorCaseView> {
  return postServiceProcessorCase(caseId, "actions", request, authorization);
}

async function postServiceProcessorCase(
  caseId: string,
  endpoint: "claim" | "actions",
  request: ServiceProcessorClaimRequest | ServiceProcessorActionRequest,
  authorization: string,
): Promise<ServiceProcessorCaseView> {
  const response = await fetch(
    `${apiBaseUrl}/service-operations/cases/${encodeURIComponent(caseId)}/${endpoint}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify(request),
    },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接人工处理案件服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `人工处理案件操作失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isServiceProcessorCaseView(payload)) {
    throw new CustomerServiceApiError("人工处理案件操作返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function loginOperator(
  request: OperatorLoginRequest,
): Promise<OperatorLoginResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/operations/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new CustomerServiceApiError("无法连接运营登录服务，请确认内部服务已启动。", 503);
  }

  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `运营登录失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isOperatorLoginResponse(payload)) {
    throw new CustomerServiceApiError("运营登录服务返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCurrentOperator(
  authorization: string,
): Promise<OperatorProfile> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/operations/me`, {
      method: "GET",
      headers: { Authorization: authorization },
    });
  } catch {
    throw new CustomerServiceApiError("无法验证运营登录状态。", 503);
  }
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `运营身份验证失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isOperatorProfile(payload)) {
    throw new CustomerServiceApiError("运营身份返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getOperationsCases(
  authorization: string,
): Promise<OperationsCase[]> {
  const response = await fetch(`${apiBaseUrl}/operations/cases`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接运营案例服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `运营案例查询失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isOperationsCase)) {
    throw new CustomerServiceApiError("运营案例返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getOperationsHandoffOverview(
  authorization: string,
  windowDays: 7 | 30 = 7,
): Promise<HandoffOverview> {
  const response = await fetch(
    `${apiBaseUrl}/operations/handoff-overview?windowDays=${windowDays}`,
    { method: "GET", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接转人工概览服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `转人工概览查询失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isHandoffOverview(payload)) {
    throw new CustomerServiceApiError("转人工概览返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function analyzeOperationsCase(
  caseId: string,
  authorization: string,
  windowDays: 7 | 30 = 7,
): Promise<OperationsAnalysisResponse> {
  const response = await fetch(
    `${apiBaseUrl}/operations/cases/${encodeURIComponent(caseId)}/analysis?windowDays=${windowDays}`,
    {
      method: "POST",
      headers: { Authorization: authorization },
    },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接运营分析服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `运营分析失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isOperationsAnalysisResponse(payload)) {
    throw new CustomerServiceApiError("运营分析返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function loginQualityDeveloper(
  request: QualityDeveloperLoginRequest,
): Promise<QualityDeveloperLoginResponse> {
  const response = await fetch(`${apiBaseUrl}/quality/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接 AI 质量开发者登录服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `开发者登录失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityDeveloperLoginResponse(payload)) {
    throw new CustomerServiceApiError("开发者登录返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getCurrentQualityDeveloper(
  authorization: string,
): Promise<QualityDeveloperProfile> {
  const response = await fetch(`${apiBaseUrl}/quality/me`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法验证 AI 质量开发者登录状态。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `开发者身份验证失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityDeveloperProfile(payload)) {
    throw new CustomerServiceApiError("开发者身份返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function runQualityEvaluation(
  authorization: string,
  executionMode: QualityEvaluationMode,
  enableAiFailureAnalysis: boolean,
): Promise<QualityEvaluationRun> {
  const response = await fetch(`${apiBaseUrl}/quality/evaluations/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: authorization },
    body: JSON.stringify({
      execution_mode: executionMode,
      enable_ai_failure_analysis: enableAiFailureAnalysis,
    }),
  }).catch(() => {
    throw new CustomerServiceApiError("无法连接 AI 质量评测服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `质量评测运行失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityEvaluationRun(payload)) {
    throw new CustomerServiceApiError("质量评测返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getLatestQualityEvaluation(
  authorization: string,
): Promise<QualityEvaluationRun> {
  const response = await fetch(`${apiBaseUrl}/quality/evaluations/latest`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法读取最新 AI 质量评测。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `质量评测读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityEvaluationRun(payload)) {
    throw new CustomerServiceApiError("质量评测返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getQualityReplayStatus(
  runId: string,
  authorization: string,
): Promise<QualityReplayStatus> {
  const response = await fetch(
    `${apiBaseUrl}/quality/evaluations/${encodeURIComponent(runId)}/replay-status`,
    { method: "GET", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法读取评测安全回放状态。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `评测回放状态读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityReplayStatus(payload)) {
    throw new CustomerServiceApiError("评测回放状态返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function replayQualityEvaluation(
  runId: string,
  authorization: string,
): Promise<QualityEvaluationRun> {
  const response = await fetch(
    `${apiBaseUrl}/quality/evaluations/${encodeURIComponent(runId)}/replay`,
    { method: "POST", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("无法连接评测安全回放服务。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `评测安全回放失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityEvaluationRun(payload)) {
    throw new CustomerServiceApiError("评测安全回放返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getQualityProfiles(
  authorization: string,
): Promise<EvaluationProfile[]> {
  const response = await fetch(`${apiBaseUrl}/quality/profiles`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法读取版本化评测 Profile。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `评测 Profile 读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isEvaluationProfile)) {
    throw new CustomerServiceApiError("评测 Profile 返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getQualityMetrics(
  authorization: string,
): Promise<QualityLocalMetric[]> {
  const response = await fetch(`${apiBaseUrl}/quality/metrics`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法读取本地质量指标。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `本地质量指标读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isQualityLocalMetric)) {
    throw new CustomerServiceApiError("本地质量指标返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function getQualityFeedbackCandidates(
  authorization: string,
): Promise<FeedbackCandidate[]> {
  const response = await fetch(`${apiBaseUrl}/quality/feedback-candidates`, {
    method: "GET",
    headers: { Authorization: authorization },
  }).catch(() => {
    throw new CustomerServiceApiError("无法读取脱敏反馈候选。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `脱敏反馈候选读取失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!Array.isArray(payload) || !payload.every(isFeedbackCandidate)) {
    throw new CustomerServiceApiError("脱敏反馈候选返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function reviewQualityFeedbackCandidate(
  candidateId: string,
  reviewStatus: "APPROVED" | "REJECTED",
  authorization: string,
): Promise<FeedbackCandidate> {
  const action = reviewStatus === "APPROVED" ? "approve" : "reject";
  const response = await fetch(
    `${apiBaseUrl}/quality/feedback-candidates/${encodeURIComponent(candidateId)}/${action}`,
    { method: "POST", headers: { Authorization: authorization } },
  ).catch(() => {
    throw new CustomerServiceApiError("脱敏反馈候选审核暂不可用。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `脱敏反馈候选审核失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isFeedbackCandidate(payload)) {
    throw new CustomerServiceApiError("脱敏反馈候选审核返回的数据格式不符合约定。", 502);
  }
  return payload;
}

export async function reviewQualityEvaluationCase(
  runId: string,
  caseId: string,
  reviewStatus: "APPROVED" | "REJECTED",
  authorization: string,
): Promise<QualityEvaluationRun> {
  const response = await fetch(
    `${apiBaseUrl}/quality/evaluations/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify({ review_status: reviewStatus }),
    },
  ).catch(() => {
    throw new CustomerServiceApiError("无法更新质量案例人工审批状态。", 503);
  });
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `质量案例审批失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isQualityEvaluationRun(payload)) {
    throw new CustomerServiceApiError("质量案例审批返回的数据格式不符合约定。", 502);
  }
  return payload;
}

async function parseJsonBody(response: Response): Promise<unknown> {
  const rawBody = await response.text();
  if (!rawBody) {
    return null;
  }
  try {
    return JSON.parse(rawBody) as unknown;
  } catch {
    return null;
  }
}

async function parseAgentTaskResponse(
  response: Response,
  actionLabel: string,
): Promise<AgentTaskPublicView> {
  const payload = await parseJsonBody(response);
  if (!response.ok) {
    throw new CustomerServiceApiError(
      extractErrorDetail(payload) || `${actionLabel}（HTTP ${response.status}）。`,
      response.status,
    );
  }
  if (!isAgentTaskPublicView(payload)) {
    throw new CustomerServiceApiError("Agent Runtime 返回的数据格式不符合公开接口约定。", 502);
  }
  return payload;
}

function extractErrorDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const detail = (payload as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : null;
}

function isCustomerServiceResponse(
  payload: unknown,
): payload is CustomerServiceResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.answer === "string";
}

function isAgentTaskPublicView(payload: unknown): payload is AgentTaskPublicView {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.task_ref === "string"
    && typeof data.goal === "string"
    && typeof data.status === "string"
    && typeof data.plan_version === "number"
    && Array.isArray(data.plan_nodes)
    && Array.isArray(data.artifacts)
    && Array.isArray(data.limitation_codes)
    && (data.context_summary === undefined || data.context_summary === null || isAgentTaskContextView(data.context_summary))
  );
}

function isAgentTaskContextView(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") return false;
  const data = payload as Record<string, unknown>;
  return (
    typeof data.version === "number"
    && typeof data.token_estimate_before === "number"
    && typeof data.token_estimate_after === "number"
    && typeof data.fact_reference_retention === "number"
  );
}

function isCustomerServiceCaseView(payload: unknown): payload is CustomerServiceCaseView {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.case_id === "string"
    && typeof data.category === "string"
    && isServiceCaseState(data.state)
    && typeof data.state_version === "number"
    && typeof data.public_status === "string"
    && typeof data.customer_information_required === "boolean"
    && typeof data.can_cancel === "boolean"
    && typeof data.can_reopen === "boolean"
  );
}

function isCustomerServiceCaseTimelineEntry(
  payload: unknown,
): payload is CustomerServiceCaseTimelineEntry {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.action_type === "string"
    && typeof data.result_code === "string"
    && typeof data.public_message === "string"
  );
}

function isCustomerFeedbackView(payload: unknown): payload is CustomerFeedbackView {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.feedback_id === "string"
    && typeof data.response_ref === "string"
    && typeof data.helpful === "boolean"
    && isCustomerFeedbackReasonCode(data.reason_code)
    && (data.review_status === "PENDING" || data.review_status === "APPROVED" || data.review_status === "REJECTED")
    && typeof data.created_at === "string"
  );
}

function isCustomerFeedbackReasonCode(value: unknown): value is CustomerFeedbackReasonCode {
  return [
    "factual_mismatch",
    "policy_not_supported",
    "unclear_explanation",
    "response_too_slow",
    "tool_unavailable",
    "other",
  ].includes(value as CustomerFeedbackReasonCode);
}

function isQualityReplayStatus(payload: unknown): payload is QualityReplayStatus {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.run_id === "string"
    && typeof data.replayable === "boolean"
    && typeof data.reason_code === "string";
}

function isEvaluationProfile(payload: unknown): payload is EvaluationProfile {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.profile_id === "string"
    && typeof data.version === "string"
    && (data.execution_mode === "contract_mock" || data.execution_mode === "live_model_synthetic")
    && (data.model_ref === "none" || data.model_ref === "configured_deepseek")
    && typeof data.prompt_version === "string"
    && typeof data.rag_profile_version === "string"
    && typeof data.tool_schema_version === "string"
    && typeof data.max_model_calls === "number"
    && typeof data.max_tool_calls === "number"
    && typeof data.timeout_seconds === "number"
    && typeof data.max_attempts === "number"
    && typeof data.active === "boolean";
}

function isQualityLocalMetric(payload: unknown): payload is QualityLocalMetric {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.name === "string"
    && typeof data.total === "number"
    && typeof data.succeeded === "number"
    && typeof data.failed === "number"
    && (data.p50_ms === undefined || data.p50_ms === null || typeof data.p50_ms === "number")
    && (data.p95_ms === undefined || data.p95_ms === null || typeof data.p95_ms === "number");
}

function isFeedbackCandidate(payload: unknown): payload is FeedbackCandidate {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.candidate_id === "string"
    && typeof data.feedback_id === "string"
    && (data.target_agent === "customer_diagnosis" || data.target_agent === "operations_analysis")
    && typeof data.sanitized_scenario === "string"
    && (data.review_status === "PENDING" || data.review_status === "APPROVED" || data.review_status === "REJECTED")
    && (data.eval_case_id === undefined || data.eval_case_id === null || typeof data.eval_case_id === "string")
    && typeof data.created_at === "string"
    && (data.reviewed_at === undefined || data.reviewed_at === null || typeof data.reviewed_at === "string");
}

function isServiceProcessorProfile(payload: unknown): payload is ServiceProcessorProfile {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.username === "string"
    && Array.isArray(data.capabilities)
    && data.capabilities.every((item) => item === "service_case_handling")
  );
}

function isServiceProcessorLoginResponse(
  payload: unknown,
): payload is ServiceProcessorLoginResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.authorization === "string" && isServiceProcessorProfile(data.processor);
}

function isServiceProcessorCaseView(payload: unknown): payload is ServiceProcessorCaseView {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.case_id === "string"
    && (data.queue_ref === "logistics_review" || data.queue_ref === "policy_review" || data.queue_ref === "general_after_sales")
    && typeof data.diagnosis_category === "string"
    && (data.priority === "low" || data.priority === "normal" || data.priority === "high")
    && isServiceCaseState(data.state)
    && typeof data.state_version === "number"
    && typeof data.assigned_to_me === "boolean"
    && typeof data.public_status === "string"
  );
}

function isServiceCaseState(value: unknown): boolean {
  return [
    "QUEUED",
    "CLAIMED",
    "AWAITING_CUSTOMER_INFORMATION",
    "IN_REVIEW",
    "RESOLVED",
    "REOPENED",
    "CLOSED",
    "CANCELLED",
  ].includes(value as string);
}

function isCustomerConversationSummary(
  payload: unknown,
): payload is CustomerConversationSummary {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.conversation_id === "string"
    && typeof data.title === "string"
    && typeof data.message_count === "number"
  );
}

function isCustomerConversationDetail(
  payload: unknown,
): payload is CustomerConversationDetail {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    isCustomerConversationSummary(data.conversation)
    && Array.isArray(data.messages)
    && data.messages.every(isCustomerConversationMessage)
  );
}

function isCustomerConversationMessage(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.message_id === "string"
    && (data.role === "user" || data.role === "assistant")
    && typeof data.content === "string"
    && (data.public_response === undefined
      || data.public_response === null
      || isCustomerServiceResponse(data.public_response))
  );
}

function isMemberProfile(payload: unknown): payload is MemberProfile {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.member_id === "number" && typeof data.username === "string";
}

function isCustomerLoginResponse(
  payload: unknown,
): payload is CustomerLoginResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.authorization === "string" && isMemberProfile(data.member);
}

function isOperatorProfile(payload: unknown): payload is OperatorProfile {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.username === "string"
    && Array.isArray(data.capabilities)
    && data.capabilities.every(
      (item) => item === "operations_analysis" || item === "case_review",
    )
  );
}

function isOperatorLoginResponse(
  payload: unknown,
): payload is OperatorLoginResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.authorization === "string" && isOperatorProfile(data.operator);
}

function isQualityDeveloperProfile(
  payload: unknown,
): payload is QualityDeveloperProfile {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.username === "string"
    && Array.isArray(data.capabilities)
    && data.capabilities.every((item) => item === "quality_evaluation")
  );
}

function isQualityDeveloperLoginResponse(
  payload: unknown,
): payload is QualityDeveloperLoginResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return typeof data.authorization === "string" && isQualityDeveloperProfile(data.developer);
}

function isQualityFailureAnalysis(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.failure_type === "string"
    && typeof data.explanation === "string"
    && typeof data.candidate_regression_case === "string"
    && typeof data.recommended_fix_area === "string"
    && data.requires_human_approval === true
  );
}

function isQualityEvaluationCase(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.case_id === "string"
    && (data.target_agent === "customer_diagnosis" || data.target_agent === "operations_analysis")
    && (data.status === "PASSED" || data.status === "FAILED")
    && typeof data.expected === "string"
    && typeof data.actual === "string"
    && Array.isArray(data.violations)
    && data.violations.every((item) => typeof item === "string")
    && (data.trajectory === undefined || data.trajectory === null || isQualityTrajectory(data.trajectory))
    && (data.review_status === "PENDING" || data.review_status === "APPROVED" || data.review_status === "REJECTED")
    && (data.environment_blocked === undefined || typeof data.environment_blocked === "boolean")
    && (data.failure_analysis === undefined || data.failure_analysis === null || isQualityFailureAnalysis(data.failure_analysis))
  );
}

function isQualityTrajectory(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    Array.isArray(data.tool_sequence)
    && data.tool_sequence.every((item) => typeof item === "string")
    && Array.isArray(data.node_sequence)
    && data.node_sequence.every((item) => typeof item === "string")
    && typeof data.step_count === "number"
    && Array.isArray(data.terminal_events)
    && data.terminal_events.every((item) => typeof item === "string")
  );
}

function isQualityEvaluationRun(payload: unknown): payload is QualityEvaluationRun {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.run_id === "string"
    && typeof data.suite_version === "string"
    && typeof data.total === "number"
    && typeof data.passed === "number"
    && typeof data.failed === "number"
    && (data.execution_mode === "contract_mock" || data.execution_mode === "live_model_synthetic")
    && typeof data.ran_at === "string"
    && typeof data.ai_failure_analysis_requested === "boolean"
    && (data.environment_blocked === undefined || typeof data.environment_blocked === "boolean")
    && (data.profile_id === undefined || typeof data.profile_id === "string")
    && (data.profile_version === undefined || typeof data.profile_version === "string")
    && (data.run_manifest === undefined || data.run_manifest === null || isQualityRunManifest(data.run_manifest))
    && Array.isArray(data.cases)
    && data.cases.every(isQualityEvaluationCase)
  );
}

function isQualityRunManifest(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return data.manifest_version === "1"
    && typeof data.correlation_ref === "string"
    && data.role === "quality_evaluation"
    && typeof data.skill_catalog_version === "string"
    && typeof data.profile_id === "string"
    && typeof data.profile_version === "string"
    && typeof data.prompt_version === "string"
    && typeof data.rag_profile_version === "string"
    && typeof data.tool_schema_version === "string"
    && typeof data.fixture_hash === "string"
    && (data.execution_mode === "contract_mock" || data.execution_mode === "live_model_synthetic")
    && typeof data.duration_ms === "number"
    && (data.result_kind === "passed" || data.result_kind === "failed" || data.result_kind === "environment_blocked")
    && typeof data.replayable === "boolean"
    && typeof data.replay_reason_code === "string";
}

function isOperationsCase(payload: unknown): payload is OperationsCase {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    typeof data.case_id === "string"
    && data.source_flow === "customer_diagnosis"
    && typeof data.diagnosis_category === "string"
    && typeof data.evidence_status === "string"
    && typeof data.handoff_reason === "string"
    && data.requires_human_review === true
    && (data.case_status === "OPEN" || data.case_status === "CLOSED")
    && data.schema_version === "1"
  );
}

function isOperationsAnalysisResponse(
  payload: unknown,
): payload is OperationsAnalysisResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  const draft = data.draft;
  const metrics = data.metrics;
  return (
    isOperationsCase(data.case)
    && !!metrics
    && typeof metrics === "object"
    && typeof (metrics as Record<string, unknown>).window_days === "number"
    && !!draft
    && typeof draft === "object"
    && typeof (draft as Record<string, unknown>).summary === "string"
    && Array.isArray((draft as Record<string, unknown>).risk_flags)
  );
}

function isHandoffOverview(payload: unknown): payload is HandoffOverview {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const data = payload as Record<string, unknown>;
  return (
    (data.window_days === 7 || data.window_days === 30)
    && typeof data.window_start === "string"
    && typeof data.window_end === "string"
    && typeof data.total_unique_handoffs === "number"
    && Array.isArray(data.categories)
    && data.categories.every((item) => {
      if (!item || typeof item !== "object") {
        return false;
      }
      const category = item as Record<string, unknown>;
      return (
        typeof category.category === "string"
        && typeof category.count === "number"
        && typeof category.percentage === "number"
      );
    })
  );
}

function isAfterSalesApplicationView(value: unknown): value is AfterSalesApplicationView {
  if (!value || typeof value !== "object") {
    return false;
  }
  const data = value as Record<string, unknown>;
  return (
    typeof data.application_id === "number"
    && typeof data.order_sn === "string"
    && (data.application_type === "cancel_refund"
      || data.application_type === "return_refund"
      || data.application_type === "exchange"
      || data.application_type === "repair")
    && typeof data.application_type_label === "string"
    && typeof data.reason === "string"
    && typeof data.status === "string"
    && typeof data.status_label === "string"
    && typeof data.fulfillment_status === "string"
    && typeof data.fulfillment_status_label === "string"
    && typeof data.can_cancel === "boolean"
    && typeof data.can_modify === "boolean"
    && typeof data.can_supplement === "boolean"
  );
}
