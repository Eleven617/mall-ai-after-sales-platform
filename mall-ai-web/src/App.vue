<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import AgentTaskWorkspace from "./AgentTaskWorkspace.vue";

import {
  createCustomerConversation,
  cancelCustomerServiceCase,
  CustomerServiceApiError,
  deleteCustomerConversation,
  getAfterSalesApplications,
  getCustomerServiceCases,
  getCustomerServiceCaseTimeline,
  getCurrentMember,
  getCustomerConversation,
  getCustomerConversations,
  loginCustomer,
  reopenCustomerServiceCase,
  sendCustomerMessage,
  submitCustomerFeedback,
  submitCustomerServiceCaseInformation,
} from "./api";
import type {
  AfterSalesApplicationView,
  AfterSalesProductOption,
  CustomerConversationSummary,
  CustomerFeedbackReasonCode,
  CustomerServiceCaseTimelineEntry,
  CustomerServiceCaseView,
  CustomerServiceResponse,
  MemberProfile,
} from "./types";

type ChatRole = "assistant" | "user" | "system";

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  response?: CustomerServiceResponse;
}

const ANONYMOUS_SESSION_KEY = "mall-ai-web:anonymous-session-id";
const TOKEN_KEY = "mall-ai-web:development-token";
const MEMBER_KEY = "mall-ai-web:member-profile";
const ACTIVE_CONVERSATION_KEY_PREFIX = "mall-ai-web:active-conversation:";
const quickPrompts = [
  "查询订单物流",
  "退货运费由谁承担？",
  "订单商品损坏，想申请退货退款",
  "我的订单能不能申请换货？",
];

const conversationElement = ref<HTMLElement | null>(null);
const messageInput = ref("");
const isSending = ref(false);
const settingsOpen = ref(false);
const accessToken = ref(readSessionValue(TOKEN_KEY));
const currentMember = ref<MemberProfile | null>(readMemberProfile());
const loginUsername = ref("");
const loginPassword = ref("");
const loginError = ref("");
const isLoggingIn = ref(false);
const afterSalesRecordsOpen = ref(false);
const isLoadingAfterSalesRecords = ref(false);
const afterSalesRecordsError = ref("");
const afterSalesApplications = ref<AfterSalesApplicationView[]>([]);
const serviceCases = ref<CustomerServiceCaseView[]>([]);
const serviceCaseTimelines = ref<Record<string, CustomerServiceCaseTimelineEntry[]>>({});
const serviceCaseDrafts = ref<Record<string, string>>({});
const serviceCaseActionId = ref("");
const feedbackReasonByResponseRef = ref<Record<string, CustomerFeedbackReasonCode>>({});
const feedbackStatusByResponseRef = ref<Record<string, string>>({});
const sessionId = ref(readOrCreateAnonymousSessionId());
const activeConversationId = ref("");
const conversationSummaries = ref<CustomerConversationSummary[]>([]);
const historyError = ref("");
const isLoadingHistory = ref(false);
const isCreatingConversation = ref(false);
const deletingConversationId = ref("");
const messages = ref<ChatMessage[]>(welcomeMessages());

const loginStateText = computed(() =>
  currentMember.value ? `已登录：${currentMember.value.username}` : "未登录",
);
const todaysConversations = computed(() =>
  conversationSummaries.value.filter((item) => isToday(item.updated_at || item.created_at)),
);
const earlierConversations = computed(() =>
  conversationSummaries.value.filter((item) => !isToday(item.updated_at || item.created_at)),
);

watch(accessToken, (value) => {
  if (value.trim()) {
    window.sessionStorage.setItem(TOKEN_KEY, value.trim());
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
});

watch(currentMember, (value) => {
  if (value) {
    window.sessionStorage.setItem(MEMBER_KEY, JSON.stringify(value));
  } else {
    window.sessionStorage.removeItem(MEMBER_KEY);
  }
});

void restoreLoginState();

async function sendMessage(rawMessage = messageInput.value): Promise<void> {
  const content = rawMessage.trim();
  if (!content || isSending.value || isCreatingConversation.value) {
    return;
  }

  if (currentMember.value && !activeConversationId.value) {
    await startNewConversation();
    if (!activeConversationId.value) {
      return;
    }
  }

  const requestSessionId = sessionId.value;
  messageInput.value = "";
  messages.value.push({ id: newId("user"), role: "user", content });
  isSending.value = true;
  await scrollToLatest();

  try {
    const response = await sendCustomerMessage(
      { session_id: requestSessionId, message: content },
      buildAuthorizationHeader(accessToken.value),
    );
    messages.value.push({
      id: newId("assistant"),
      role: "assistant",
      content: response.answer,
      response,
    });
    if (response.submitted_after_sales_application) {
      upsertAfterSalesApplication(response.submitted_after_sales_application);
    }
    if (response.after_sales_applications?.length) {
      response.after_sales_applications.forEach(upsertAfterSalesApplication);
    }
    if (currentMember.value && requestSessionId === activeConversationId.value) {
      void refreshConversationSummaries();
    }
  } catch (error) {
    const failureMessage =
      error instanceof CustomerServiceApiError
        ? error.message
        : "请求未完成，请稍后重试。";
    messages.value.push({ id: newId("error"), role: "system", content: failureMessage });
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    isSending.value = false;
    await scrollToLatest();
  }
}

async function login(): Promise<void> {
  const username = loginUsername.value.trim();
  if (!username || !loginPassword.value) {
    loginError.value = "请输入用户名和密码。";
    return;
  }

  isLoggingIn.value = true;
  loginError.value = "";
  try {
    const result = await loginCustomer({ username, password: loginPassword.value });
    accessToken.value = result.authorization;
    currentMember.value = result.member;
    loginPassword.value = "";
    settingsOpen.value = false;
    await initializeAuthenticatedWorkspace();
  } catch (error) {
    loginError.value =
      error instanceof CustomerServiceApiError
        ? error.message
        : "登录未完成，请稍后重试。";
  } finally {
    isLoggingIn.value = false;
  }
}

function logout(): void {
  clearAuthenticationState();
  settingsOpen.value = false;
}

async function restoreLoginState(): Promise<void> {
  if (!accessToken.value.trim()) {
    return;
  }
  try {
    currentMember.value = await getCurrentMember(
      buildAuthorizationHeader(accessToken.value) || accessToken.value,
    );
    await initializeAuthenticatedWorkspace();
  } catch {
    clearAuthenticationState();
  }
}

function clearAuthenticationState(): void {
  accessToken.value = "";
  currentMember.value = null;
  afterSalesRecordsOpen.value = false;
  afterSalesRecordsError.value = "";
  afterSalesApplications.value = [];
  serviceCases.value = [];
  serviceCaseTimelines.value = {};
  serviceCaseDrafts.value = {};
  serviceCaseActionId.value = "";
  conversationSummaries.value = [];
  activeConversationId.value = "";
  historyError.value = "";
  startAnonymousConversation();
}

async function initializeAuthenticatedWorkspace(): Promise<void> {
  if (!currentMember.value) {
    return;
  }
  activeConversationId.value = "";
  conversationSummaries.value = [];
  messages.value = welcomeMessages();
  await refreshConversationSummaries();
  if (!currentMember.value) {
    return;
  }
  const savedId = readActiveConversationId(currentMember.value.member_id);
  const existing = conversationSummaries.value.find(
    (item) => item.conversation_id === savedId,
  );
  if (existing) {
    await openConversation(existing);
  } else {
    await startNewConversation();
  }
}

async function refreshConversationSummaries(): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization || !currentMember.value) {
    return;
  }
  isLoadingHistory.value = true;
  historyError.value = "";
  try {
    conversationSummaries.value = await getCustomerConversations(authorization);
  } catch (error) {
    historyError.value = messageFor(error, "历史会话暂时无法读取，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    isLoadingHistory.value = false;
  }
}

async function startNewConversation(): Promise<void> {
  if (isCreatingConversation.value || isSending.value) {
    return;
  }
  if (!currentMember.value) {
    startAnonymousConversation();
    return;
  }
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization) {
    clearAuthenticationState();
    return;
  }

  isCreatingConversation.value = true;
  historyError.value = "";
  try {
    const summary = await createCustomerConversation(newConversationId(), authorization);
    conversationSummaries.value = [
      summary,
      ...conversationSummaries.value.filter(
        (item) => item.conversation_id !== summary.conversation_id,
      ),
    ];
    activateConversation(summary);
  } catch (error) {
    historyError.value = messageFor(error, "新建会话未完成，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    isCreatingConversation.value = false;
  }
}

async function openConversation(summary: CustomerConversationSummary): Promise<void> {
  if (isSending.value || isLoadingHistory.value || !currentMember.value) {
    return;
  }
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization) {
    clearAuthenticationState();
    return;
  }

  isLoadingHistory.value = true;
  historyError.value = "";
  try {
    const detail = await getCustomerConversation(summary.conversation_id, authorization);
    activeConversationId.value = detail.conversation.conversation_id;
    sessionId.value = detail.conversation.conversation_id;
    persistActiveConversationId();
    messages.value = detail.messages.length
      ? detail.messages.map((message) => ({
          id: message.message_id,
          role: message.role,
          content: message.content,
          response: message.public_response || undefined,
        }))
      : welcomeMessages();
    await scrollToLatest();
  } catch (error) {
    historyError.value = messageFor(error, "历史会话暂时无法打开，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    isLoadingHistory.value = false;
  }
}

async function removeConversation(summary: CustomerConversationSummary): Promise<void> {
  if (isSending.value || deletingConversationId.value || !currentMember.value) {
    return;
  }
  if (!window.confirm(`删除“${summary.title}”吗？删除后无法恢复。`)) {
    return;
  }
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization) {
    clearAuthenticationState();
    return;
  }

  deletingConversationId.value = summary.conversation_id;
  historyError.value = "";
  try {
    await deleteCustomerConversation(summary.conversation_id, authorization);
    conversationSummaries.value = conversationSummaries.value.filter(
      (item) => item.conversation_id !== summary.conversation_id,
    );
    if (activeConversationId.value === summary.conversation_id) {
      activeConversationId.value = "";
      persistActiveConversationId();
      const replacement = conversationSummaries.value[0];
      if (replacement) {
        await openConversation(replacement);
      } else {
        startEmptyAuthenticatedConversation();
      }
    }
  } catch (error) {
    historyError.value = messageFor(error, "历史会话暂时无法删除，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    deletingConversationId.value = "";
  }
}

function activateConversation(summary: CustomerConversationSummary): void {
  activeConversationId.value = summary.conversation_id;
  sessionId.value = summary.conversation_id;
  persistActiveConversationId();
  messages.value = welcomeMessages();
}

function startAnonymousConversation(): void {
  sessionId.value = newId("session");
  window.localStorage.setItem(ANONYMOUS_SESSION_KEY, sessionId.value);
  messages.value = welcomeMessages();
}

function startEmptyAuthenticatedConversation(): void {
  sessionId.value = newConversationId();
  messages.value = welcomeMessages();
}

function persistActiveConversationId(): void {
  if (!currentMember.value) {
    return;
  }
  const key = activeConversationStorageKey(currentMember.value.member_id);
  if (activeConversationId.value) {
    window.localStorage.setItem(key, activeConversationId.value);
  } else {
    window.localStorage.removeItem(key);
  }
}

async function openAfterSalesRecords(): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization) {
    settingsOpen.value = true;
    return;
  }

  afterSalesRecordsOpen.value = true;
  isLoadingAfterSalesRecords.value = true;
  afterSalesRecordsError.value = "";
  try {
    const [applications, cases] = await Promise.all([
      getAfterSalesApplications(authorization),
      getCustomerServiceCases(authorization),
    ]);
    afterSalesApplications.value = applications;
    serviceCases.value = cases;
  } catch (error) {
    afterSalesRecordsError.value = messageFor(error, "售后记录暂时无法加载，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      clearAuthenticationState();
    }
  } finally {
    isLoadingAfterSalesRecords.value = false;
  }
}

function upsertAfterSalesApplication(application: AfterSalesApplicationView): void {
  const existingIndex = afterSalesApplications.value.findIndex(
    (item) => item.application_id === application.application_id,
  );
  if (existingIndex === -1) {
    afterSalesApplications.value = [application, ...afterSalesApplications.value];
    return;
  }
  const next = [...afterSalesApplications.value];
  next[existingIndex] = application;
  afterSalesApplications.value = next;
}

function upsertServiceCase(value: CustomerServiceCaseView): void {
  const index = serviceCases.value.findIndex((item) => item.case_id === value.case_id);
  if (index === -1) {
    serviceCases.value = [value, ...serviceCases.value];
    return;
  }
  const next = [...serviceCases.value];
  next[index] = value;
  serviceCases.value = next;
}

async function loadServiceCaseTimeline(value: CustomerServiceCaseView): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization) return;
  try {
    serviceCaseTimelines.value = {
      ...serviceCaseTimelines.value,
      [value.case_id]: await getCustomerServiceCaseTimeline(value.case_id, authorization),
    };
  } catch (error) {
    afterSalesRecordsError.value = messageFor(error, "人工协同进度暂时无法读取，请稍后重试。");
  }
}

async function submitServiceCaseInformation(value: CustomerServiceCaseView): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  const information = (serviceCaseDrafts.value[value.case_id] || "").trim();
  if (!authorization || !information || serviceCaseActionId.value) return;
  if (!value.required_information_type) {
    afterSalesRecordsError.value = "该事项缺少服务端指定的补件类型，请刷新后重试。";
    return;
  }
  serviceCaseActionId.value = value.case_id;
  try {
    const updated = await submitCustomerServiceCaseInformation(
      value.case_id,
      {
        expected_version: value.state_version,
        idempotency_key: newIdempotencyKey(),
        information_type: value.required_information_type,
        information,
      },
      authorization,
    );
    upsertServiceCase(updated);
    serviceCaseDrafts.value = { ...serviceCaseDrafts.value, [value.case_id]: "" };
    await loadServiceCaseTimeline(updated);
  } catch (error) {
    afterSalesRecordsError.value = messageFor(error, "补充信息未提交，请稍后重试。");
  } finally {
    serviceCaseActionId.value = "";
  }
}

function serviceCaseInformationLabel(value: CustomerServiceCaseView): string {
  if (value.required_information_type === "purchase_context") return "请补充购买或使用背景";
  if (value.required_information_type === "problem_description") return "请补充问题说明";
  return "需要补充的信息";
}

async function cancelServiceCase(value: CustomerServiceCaseView): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!authorization || !value.can_cancel || serviceCaseActionId.value) return;
  if (!window.confirm("确认取消这个人工协同事项吗？这不会取消任何已提交的售后申请。")) return;
  serviceCaseActionId.value = value.case_id;
  try {
    const updated = await cancelCustomerServiceCase(
      value.case_id,
      { expected_version: value.state_version, idempotency_key: newIdempotencyKey() },
      authorization,
    );
    upsertServiceCase(updated);
    await loadServiceCaseTimeline(updated);
  } catch (error) {
    afterSalesRecordsError.value = messageFor(error, "人工协同事项未取消，请稍后重试。");
  } finally {
    serviceCaseActionId.value = "";
  }
}

async function reopenServiceCase(value: CustomerServiceCaseView): Promise<void> {
  const authorization = buildAuthorizationHeader(accessToken.value);
  const reason = (serviceCaseDrafts.value[value.case_id] || "").trim();
  if (!authorization || !value.can_reopen || !reason || serviceCaseActionId.value) return;
  serviceCaseActionId.value = value.case_id;
  try {
    const updated = await reopenCustomerServiceCase(
      value.case_id,
      { expected_version: value.state_version, idempotency_key: newIdempotencyKey(), reason },
      authorization,
    );
    upsertServiceCase(updated);
    serviceCaseDrafts.value = { ...serviceCaseDrafts.value, [value.case_id]: "" };
    await loadServiceCaseTimeline(updated);
  } catch (error) {
    afterSalesRecordsError.value = messageFor(error, "人工协同事项未重新开启，请稍后重试。");
  } finally {
    serviceCaseActionId.value = "";
  }
}

function feedbackReason(responseRef: string): CustomerFeedbackReasonCode {
  return feedbackReasonByResponseRef.value[responseRef] || "other";
}

function setFeedbackReason(responseRef: string, event: Event): void {
  const value = (event.target as HTMLSelectElement | null)?.value || "";
  const allowed: CustomerFeedbackReasonCode[] = [
    "factual_mismatch",
    "policy_not_supported",
    "unclear_explanation",
    "response_too_slow",
    "tool_unavailable",
    "other",
  ];
  if (allowed.includes(value as CustomerFeedbackReasonCode)) {
    feedbackReasonByResponseRef.value = {
      ...feedbackReasonByResponseRef.value,
      [responseRef]: value as CustomerFeedbackReasonCode,
    };
  }
}

async function submitResponseFeedback(
  response: CustomerServiceResponse,
  helpful: boolean,
): Promise<void> {
  const responseRef = response.response_ref;
  const authorization = buildAuthorizationHeader(accessToken.value);
  if (!responseRef || !authorization || feedbackStatusByResponseRef.value[responseRef] === "正在提交") return;
  feedbackStatusByResponseRef.value = { ...feedbackStatusByResponseRef.value, [responseRef]: "正在提交" };
  try {
    await submitCustomerFeedback(
      { response_ref: responseRef, helpful, reason_code: feedbackReason(responseRef), consent: true },
      authorization,
    );
    feedbackStatusByResponseRef.value = { ...feedbackStatusByResponseRef.value, [responseRef]: "已收到反馈" };
  } catch (error) {
    feedbackStatusByResponseRef.value = { ...feedbackStatusByResponseRef.value, [responseRef]: messageFor(error, "反馈暂未提交") };
  }
}

function requestAfterSalesCancellation(application: AfterSalesApplicationView): void {
  if (isSending.value || !application.can_cancel) {
    return;
  }
  void sendMessage(`取消售后申请 #${application.application_id}`);
}

function requestAfterSalesModification(application: AfterSalesApplicationView): void {
  if (isSending.value || !application.can_modify) {
    return;
  }
  void sendMessage(`修改售后申请 #${application.application_id}`);
}

function formatAfterSalesTime(timestamp?: number | null): string {
  if (!timestamp) {
    return "暂未更新";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

function formatConversationTime(value?: string | null): string {
  if (!value) {
    return "刚刚";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间不可用";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function isToday(value?: string | null): boolean {
  if (!value) {
    return true;
  }
  const date = new Date(value);
  const today = new Date();
  return (
    !Number.isNaN(date.getTime())
    && date.getFullYear() === today.getFullYear()
    && date.getMonth() === today.getMonth()
    && date.getDate() === today.getDate()
  );
}

function chooseProduct(product: AfterSalesProductOption): void {
  const attribute = product.product_attr ? `（${product.product_attr}）` : "";
  void sendMessage(`我选择${product.product_name}${attribute}`);
}

function buildAuthorizationHeader(token: string): string | undefined {
  const normalized = token.trim();
  if (!normalized) {
    return undefined;
  }
  return normalized.startsWith("Bearer ") ? normalized : `Bearer ${normalized}`;
}

function missingFieldLabel(field: string): string {
  const labels: Record<string, string> = {
    order_sn: "订单号",
    product: "售后商品",
    reason: "售后原因",
    application_type: "售后类型",
  };
  return labels[field] || field;
}

function diagnosisCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    delivery_in_transit: "物流仍在运输或派送中",
    delivery_exception: "物流存在异常状态",
    order_state_review: "已完成订单状态核验",
    policy_insufficient: "政策依据不足",
    tool_failure: "自动诊断未完成",
    needs_order_identifier: "还需要订单号",
  };
  return labels[category] || "订单问题诊断";
}

function diagnosisEvidenceLabel(status: string): string {
  const labels: Record<string, string> = {
    complete: "信息完整",
    partial: "信息部分完整",
    insufficient: "信息不足",
    unavailable: "查询暂不可用",
  };
  return labels[status] || "信息待确认";
}

function diagnosisNextStepLabel(step: string): string {
  const labels: Record<string, string> = {
    continue_after_sales: "进入售后流程",
    contact_human: "联系人工客服",
    retry_diagnosis: "稍后重试",
    provide_order_sn: "补充订单号",
  };
  return labels[step] || step;
}

function messageFor(error: unknown, fallback: string): string {
  return error instanceof CustomerServiceApiError ? error.message : fallback;
}

function readSessionValue(key: string): string {
  return typeof window === "undefined" ? "" : window.sessionStorage.getItem(key) || "";
}

function readMemberProfile(): MemberProfile | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.sessionStorage.getItem(MEMBER_KEY);
  if (!raw) {
    return null;
  }
  try {
    const value = JSON.parse(raw) as Partial<MemberProfile>;
    if (typeof value.member_id === "number" && typeof value.username === "string") {
      return { member_id: value.member_id, username: value.username };
    }
  } catch {
    // A damaged browser cache is ignored and replaced at the next login.
  }
  return null;
}

function readOrCreateAnonymousSessionId(): string {
  if (typeof window === "undefined") {
    return newId("session");
  }
  const existing = window.localStorage.getItem(ANONYMOUS_SESSION_KEY);
  if (existing) {
    return existing;
  }
  const created = newId("session");
  window.localStorage.setItem(ANONYMOUS_SESSION_KEY, created);
  return created;
}

function activeConversationStorageKey(memberId: number): string {
  return `${ACTIVE_CONVERSATION_KEY_PREFIX}${memberId}`;
}

function readActiveConversationId(memberId: number): string {
  return window.localStorage.getItem(activeConversationStorageKey(memberId)) || "";
}

function newConversationId(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  const segments = [8, 4, 4, 4, 12];
  return segments
    .map((length) => Math.random().toString(16).slice(2).padEnd(length, "0").slice(0, length))
    .join("-");
}

function newId(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
  return `${prefix}-${random}`;
}

function newIdempotencyKey(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID().replace(/-/g, "");
  }
  let result = "";
  while (result.length < 32) result += Math.random().toString(16).slice(2);
  return result.slice(0, 32).padEnd(32, "0");
}

function welcomeMessages(): ChatMessage[] {
  return [
    {
      id: newId("welcome"),
      role: "assistant",
      content:
        "你好，我可以协助查询订单、物流和售后政策。涉及退货申请时，我会先展示方案，再等你明确确认。",
    },
  ];
}

async function scrollToLatest(): Promise<void> {
  await nextTick();
  conversationElement.value?.scrollTo({
    top: conversationElement.value.scrollHeight,
    behavior: "smooth",
  });
}
</script>

<template>
  <main class="application-shell">
    <section class="product-panel" aria-label="智能售后客服">
      <header class="topbar">
        <div class="brand-block">
          <span class="brand-mark" aria-hidden="true">AI</span>
          <div>
            <p class="eyebrow">MALL SUPPORT</p>
            <h1>商城售后咨询</h1>
          </div>
        </div>
        <div class="topbar-actions">
          <span class="status-pill" :class="{ active: currentMember }">
            <span class="status-dot" aria-hidden="true"></span>
            {{ loginStateText }}
          </span>
          <button
            v-if="currentMember"
            class="text-button"
            type="button"
            :disabled="isLoadingAfterSalesRecords"
            @click="openAfterSalesRecords"
          >
            售后记录
          </button>
          <button class="text-button" type="button" @click="settingsOpen = !settingsOpen">
            {{ settingsOpen ? "收起账号" : currentMember ? "账号" : "登录" }}
          </button>
          <a class="employee-link" href="/operations">运营入口</a>
          <a class="employee-link" href="/service-operations">人工处理</a>
        </div>
      </header>

      <section v-if="settingsOpen" class="account-panel" aria-label="商城账号登录">
        <div v-if="currentMember" class="account-summary">
          <div>
            <p class="settings-title">当前商城账号</p>
            <p class="settings-description">{{ currentMember.username }}。历史咨询只会保存在当前账号下。</p>
          </div>
          <button class="secondary-button" type="button" @click="logout">退出登录</button>
        </div>
        <form v-else class="login-form" @submit.prevent="login">
          <div>
            <p class="settings-title">登录商城账号</p>
            <p class="settings-description">登录后可保存、继续和删除自己的历史咨询；不同账号之间不会互相看到会话。</p>
          </div>
          <label class="login-field">
            <span>用户名</span>
            <input v-model="loginUsername" type="text" autocomplete="username" placeholder="输入商城用户名" />
          </label>
          <label class="login-field">
            <span>密码</span>
            <input v-model="loginPassword" type="password" autocomplete="current-password" placeholder="输入商城密码" />
          </label>
          <button class="primary-button login-button" type="submit" :disabled="isLoggingIn">
            {{ isLoggingIn ? "登录中" : "登录" }}
          </button>
          <p v-if="loginError" class="login-error" role="alert">{{ loginError }}</p>
        </form>
      </section>

      <section v-if="afterSalesRecordsOpen" class="return-records-panel" aria-label="我的售后记录">
        <div class="return-records-heading">
          <div>
            <p class="panel-kicker">我的售后</p>
            <h2>售后处理进度</h2>
          </div>
          <div class="return-records-actions">
            <button class="text-button" type="button" :disabled="isLoadingAfterSalesRecords" @click="openAfterSalesRecords">刷新</button>
            <button class="text-button" type="button" @click="afterSalesRecordsOpen = false">关闭</button>
          </div>
        </div>
        <p v-if="isLoadingAfterSalesRecords" class="return-records-note">正在读取当前账号的售后记录...</p>
        <p v-else-if="afterSalesRecordsError" class="return-records-error">{{ afterSalesRecordsError }}</p>
        <p v-else-if="!afterSalesApplications.length" class="return-records-note">当前账号还没有通过智能客服提交的售后申请。</p>
        <div v-else class="return-record-list">
          <article v-for="application in afterSalesApplications" :key="application.application_id" class="return-record-item">
            <div class="return-record-title">
              <div><p class="card-caption">{{ application.application_type_label }} · 售后单 #{{ application.application_id }}</p><h3>{{ application.product_name || "整笔订单" }}</h3></div>
              <span class="return-status" :class="application.status">{{ application.status_label }}</span>
            </div>
            <dl>
              <div><dt>申请类型</dt><dd>{{ application.application_type_label }}</dd></div>
              <div><dt>订单号</dt><dd>{{ application.order_sn }}</dd></div>
              <div><dt>原因</dt><dd>{{ application.reason }}</dd></div>
              <div v-if="application.description"><dt>说明</dt><dd>{{ application.description }}</dd></div>
               <div><dt>提交时间</dt><dd>{{ formatAfterSalesTime(application.created_at) }}</dd></div>
               <div v-if="application.updated_at"><dt>最近更新</dt><dd>{{ formatAfterSalesTime(application.updated_at) }}</dd></div>
               <div v-if="application.handling_note"><dt>处理说明</dt><dd>{{ application.handling_note }}</dd></div>
               <div><dt>履约状态</dt><dd>{{ application.fulfillment_status_label }}</dd></div>
               <div v-if="application.fulfillment_note"><dt>履约说明</dt><dd>{{ application.fulfillment_note }}</dd></div>
            </dl>
            <div v-if="application.can_cancel || application.can_modify" class="record-actions">
              <button v-if="application.can_modify" class="secondary-button" type="button" :disabled="isSending" @click="requestAfterSalesModification(application)">修改说明</button>
              <button v-if="application.can_cancel" class="secondary-button danger-button" type="button" :disabled="isSending" @click="requestAfterSalesCancellation(application)">取消申请</button>
            </div>
          </article>
        </div>
        <section class="service-case-records" aria-label="人工协同事项">
          <div class="return-record-title">
            <div><p class="card-caption">人工协同</p><h3>需要人工跟进的事项</h3></div>
            <span class="return-status">{{ serviceCases.length }} 项</span>
          </div>
          <p v-if="!isLoadingAfterSalesRecords && !serviceCases.length" class="return-records-note">当前账号没有需要人工协同处理的事项。</p>
          <div v-else class="return-record-list">
            <article v-for="caseItem in serviceCases" :key="caseItem.case_id" class="return-record-item service-case-item">
              <div class="return-record-title">
                <div><p class="card-caption">人工协同进度</p><h3>{{ diagnosisCategoryLabel(caseItem.category) }}</h3></div>
                <span class="return-status">{{ caseItem.state }}</span>
              </div>
              <dl>
                <div><dt>当前状态</dt><dd>{{ caseItem.public_status }}</dd></div>
                <div v-if="caseItem.last_public_message"><dt>处理说明</dt><dd>{{ caseItem.last_public_message }}</dd></div>
                <div><dt>最近更新</dt><dd>{{ formatConversationTime(caseItem.updated_at) }}</dd></div>
              </dl>
              <div v-if="caseItem.customer_information_required || caseItem.can_reopen" class="service-case-input">
                <label>{{ caseItem.customer_information_required ? serviceCaseInformationLabel(caseItem) : "重新开启说明" }}</label>
                <textarea v-model="serviceCaseDrafts[caseItem.case_id]" :disabled="serviceCaseActionId === caseItem.case_id" rows="2" maxlength="180" placeholder="请勿填写电话、地址、凭证或其他敏感信息"></textarea>
                <button v-if="caseItem.customer_information_required" class="primary-button" type="button" :disabled="serviceCaseActionId === caseItem.case_id || !(serviceCaseDrafts[caseItem.case_id] || '').trim()" @click="submitServiceCaseInformation(caseItem)">提交补充信息</button>
                <button v-else class="primary-button" type="button" :disabled="serviceCaseActionId === caseItem.case_id || !(serviceCaseDrafts[caseItem.case_id] || '').trim()" @click="reopenServiceCase(caseItem)">重新开启事项</button>
              </div>
              <div class="record-actions">
                <button class="secondary-button" type="button" :disabled="serviceCaseActionId === caseItem.case_id" @click="loadServiceCaseTimeline(caseItem)">查看进度</button>
                <button v-if="caseItem.can_cancel" class="secondary-button danger-button" type="button" :disabled="serviceCaseActionId === caseItem.case_id" @click="cancelServiceCase(caseItem)">取消协同事项</button>
              </div>
              <ol v-if="serviceCaseTimelines[caseItem.case_id]?.length" class="service-case-timeline">
                <li v-for="entry in serviceCaseTimelines[caseItem.case_id]" :key="`${entry.action_type}-${entry.created_at || ''}-${entry.public_message}`"><span>{{ formatConversationTime(entry.created_at) }}</span><strong>{{ entry.public_message }}</strong></li>
              </ol>
            </article>
          </div>
        </section>
      </section>

      <AgentTaskWorkspace
        v-if="currentMember"
        :authorization="buildAuthorizationHeader(accessToken) || ''"
        :session-id="sessionId"
      />

      <div class="workspace">
        <aside class="history-sidebar" aria-label="历史会话">
          <div class="history-heading">
            <div><p class="panel-kicker">咨询记录</p><h2>历史会话</h2></div>
            <button class="new-conversation-button" type="button" :disabled="isCreatingConversation || isSending" @click="startNewConversation">
              {{ isCreatingConversation ? "创建中" : "新建会话" }}
            </button>
          </div>
          <p v-if="!currentMember" class="history-login-note">登录后可保存历史咨询，并在下次继续。</p>
          <p v-else-if="isLoadingHistory" class="history-note">正在读取会话...</p>
          <p v-else-if="historyError" class="history-error">{{ historyError }}</p>
          <template v-else>
            <section v-if="todaysConversations.length" class="history-group">
              <h3>今天</h3>
              <div class="history-list">
                <article v-for="item in todaysConversations" :key="item.conversation_id" class="history-item" :class="{ active: item.conversation_id === activeConversationId }">
                  <button class="history-open-button" type="button" @click="openConversation(item)">
                    <strong>{{ item.title }}</strong><span>{{ formatConversationTime(item.updated_at || item.created_at) }}</span>
                  </button>
                  <button class="history-delete-button" type="button" :disabled="deletingConversationId === item.conversation_id" :aria-label="`删除 ${item.title}`" @click="removeConversation(item)">×</button>
                </article>
              </div>
            </section>
            <section v-if="earlierConversations.length" class="history-group">
              <h3>更早</h3>
              <div class="history-list">
                <article v-for="item in earlierConversations" :key="item.conversation_id" class="history-item" :class="{ active: item.conversation_id === activeConversationId }">
                  <button class="history-open-button" type="button" @click="openConversation(item)">
                    <strong>{{ item.title }}</strong><span>{{ formatConversationTime(item.updated_at || item.created_at) }}</span>
                  </button>
                  <button class="history-delete-button" type="button" :disabled="deletingConversationId === item.conversation_id" :aria-label="`删除 ${item.title}`" @click="removeConversation(item)">×</button>
                </article>
              </div>
            </section>
            <p v-if="currentMember && !conversationSummaries.length" class="history-note">还没有历史咨询。</p>
          </template>
        </aside>

        <section class="chat-panel" aria-label="客服对话">
          <div ref="conversationElement" class="conversation" aria-live="polite">
            <section
              v-if="messages.length && messages[messages.length - 1].response?.task"
              class="task-status-card"
              aria-label="已暂存任务"
            >
              <div>
                <p class="card-caption">{{ messages[messages.length - 1].response?.task?.task_status === "paused" ? "已暂存任务" : "当前处理任务" }}</p>
                <h3>{{ messages[messages.length - 1].response?.task?.task_label }}</h3>
                <p>{{ messages[messages.length - 1].response?.task?.task_hint }}</p>
              </div>
              <span class="return-status">{{ messages[messages.length - 1].response?.task?.task_status === "paused" ? "可恢复" : "进行中" }}</span>
            </section>
            <article v-for="item in messages" :key="item.id" class="message-row" :class="item.role">
              <div v-if="item.role !== 'user'" class="avatar" aria-hidden="true">AI</div>
              <div class="message-stack">
                <p class="message-author">{{ item.role === "user" ? "你" : item.role === "system" ? "系统提示" : "智能客服" }}</p>
                <div class="message-bubble"><p class="message-content">{{ item.content }}</p></div>

                <section v-if="item.role === 'assistant' && currentMember && item.response?.response_ref" class="feedback-card">
                  <span>这条回答有帮助吗？</span>
                  <select :value="feedbackReason(item.response.response_ref)" @change="setFeedbackReason(item.response.response_ref, $event)">
                    <option value="factual_mismatch">事实不符</option><option value="policy_not_supported">政策依据不足</option><option value="unclear_explanation">解释不清</option><option value="response_too_slow">响应太慢</option><option value="tool_unavailable">查询服务不可用</option><option value="other">其他</option>
                  </select>
                  <button type="button" class="text-button" :disabled="feedbackStatusByResponseRef[item.response.response_ref] === '正在提交'" @click="submitResponseFeedback(item.response, true)">有帮助</button>
                  <button type="button" class="text-button" :disabled="feedbackStatusByResponseRef[item.response.response_ref] === '正在提交'" @click="submitResponseFeedback(item.response, false)">没帮助</button>
                  <small v-if="feedbackStatusByResponseRef[item.response.response_ref]">{{ feedbackStatusByResponseRef[item.response.response_ref] }}</small>
                </section>

                <section v-for="card in item.response?.verified_facts || []" :key="`${item.id}-${card.source}`" class="evidence-card facts-card">
                  <p class="card-caption">查询结果</p><h3>{{ card.title }}</h3>
                  <dl><div v-for="field in card.fields" :key="field.label"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
                </section>

                <section v-if="item.response?.diagnosis" class="workflow-card diagnosis-card">
                  <p class="card-caption">问题处理建议</p><h3>{{ diagnosisCategoryLabel(item.response.diagnosis.category) }}</h3>
                  <p class="diagnosis-status">{{ diagnosisEvidenceLabel(item.response.diagnosis.evidence_status) }}</p>
                  <div v-if="item.response.diagnosis.allowed_next_steps.length" class="diagnosis-next-steps"><span v-for="step in item.response.diagnosis.allowed_next_steps" :key="step">{{ diagnosisNextStepLabel(step) }}</span></div>
                  <p v-if="item.response.diagnosis.handoff" class="diagnosis-handoff">{{ item.response.diagnosis.handoff.summary }}</p>
                </section>

                <section v-if="item.response?.after_sales_draft" class="workflow-card">
                  <p class="card-caption">售后信息收集中</p><h3>还需要补充</h3>
                  <div class="missing-fields"><span v-for="field in item.response.after_sales_draft.missing_fields" :key="field">{{ missingFieldLabel(field) }}</span></div>
                  <div v-if="item.response.after_sales_draft.product_options.length" class="product-options">
                    <p>请选择要处理的商品：</p>
                    <button v-for="product in item.response.after_sales_draft.product_options" :key="`${product.product_name}-${product.product_attr || ''}`" type="button" :disabled="isSending" @click="chooseProduct(product)">
                      <strong>{{ product.product_name }}</strong><span v-if="product.product_attr">{{ product.product_attr }}</span>
                    </button>
                  </div>
                </section>

                <section v-if="item.response?.after_sales_eligibility" class="workflow-card eligibility-card">
                  <p class="card-caption">订单资格核验</p><h3>{{ item.response.after_sales_eligibility.application_type_label }}</h3>
                  <dl>
                    <div><dt>订单号</dt><dd>{{ item.response.after_sales_eligibility.order_sn }}</dd></div>
                    <div><dt>订单状态</dt><dd>{{ item.response.after_sales_eligibility.order_status }}</dd></div>
                    <div><dt>核验结果</dt><dd>{{ item.response.after_sales_eligibility.eligible ? "当前可提交" : "当前不可提交" }}</dd></div>
                  </dl>
                </section>

                <section v-if="item.response?.after_sales_proposal" class="workflow-card proposal-card">
                  <p class="card-caption">待确认售后方案</p><h3>{{ item.response.after_sales_proposal.application_type_label }} · {{ item.response.after_sales_proposal.product_name }}</h3>
                  <dl>
                    <div><dt>订单号</dt><dd>{{ item.response.after_sales_proposal.order_sn }}</dd></div>
                    <div><dt>原因</dt><dd>{{ item.response.after_sales_proposal.reason }}</dd></div>
                    <div><dt>说明</dt><dd>{{ item.response.after_sales_proposal.description }}</dd></div>
                  </dl>
                  <div class="proposal-actions">
                    <button class="primary-button" type="button" :disabled="isSending" @click="sendMessage('确认')">确认提交售后申请</button>
                    <button class="secondary-button" type="button" :disabled="isSending" @click="sendMessage('取消')">暂不提交</button>
                  </div>
                </section>

                <section v-if="item.response?.submitted_after_sales_application" class="workflow-card submitted-return-card">
                  <p class="card-caption">{{ item.response.after_sales_completed_action === 'cancel' ? '售后申请已取消' : item.response.after_sales_completed_action === 'modify' ? '售后申请已更新' : '售后申请已提交' }}</p>
                  <div class="submitted-return-heading"><h3>{{ item.response.submitted_after_sales_application.application_type_label }} · 售后单 #{{ item.response.submitted_after_sales_application.application_id }}</h3><span class="return-status" :class="item.response.submitted_after_sales_application.status">{{ item.response.submitted_after_sales_application.status_label }}</span></div>
                  <dl>
                    <div><dt>商品</dt><dd>{{ item.response.submitted_after_sales_application.product_name || "整笔订单" }}</dd></div>
                    <div><dt>订单号</dt><dd>{{ item.response.submitted_after_sales_application.order_sn }}</dd></div>
                    <div><dt>提交时间</dt><dd>{{ formatAfterSalesTime(item.response.submitted_after_sales_application.created_at) }}</dd></div>
                    <div><dt>履约状态</dt><dd>{{ item.response.submitted_after_sales_application.fulfillment_status_label }}</dd></div>
                    <div v-if="item.response.submitted_after_sales_application.fulfillment_note"><dt>履约说明</dt><dd>{{ item.response.submitted_after_sales_application.fulfillment_note }}</dd></div>
                  </dl>
                </section>

                <section v-if="item.response?.after_sales_pending_action" class="workflow-card proposal-card">
                  <p class="card-caption">待确认售后操作</p>
                  <h3>{{ item.response.after_sales_pending_action.application_type_label }} · 售后单 #{{ item.response.after_sales_pending_action.application_id }}</h3>
                  <p>{{ item.response.after_sales_pending_action.impact_summary }}</p>
                  <dl v-if="item.response.after_sales_pending_action.reason || item.response.after_sales_pending_action.description">
                    <div v-if="item.response.after_sales_pending_action.reason"><dt>变更原因</dt><dd>{{ item.response.after_sales_pending_action.reason }}</dd></div>
                    <div v-if="item.response.after_sales_pending_action.description"><dt>补充说明</dt><dd>{{ item.response.after_sales_pending_action.description }}</dd></div>
                  </dl>
                  <div class="proposal-actions">
                    <button class="primary-button" type="button" :disabled="isSending" @click="sendMessage('确认')">确认{{ item.response.after_sales_pending_action.action === 'cancel' ? '取消' : '修改' }}</button>
                    <button class="secondary-button" type="button" :disabled="isSending" @click="sendMessage('取消')">暂不操作</button>
                  </div>
                </section>

                <section v-if="item.response?.after_sales_selection" class="workflow-card">
                  <p class="card-caption">选择售后申请</p><h3>请先选择目标申请</h3>
                  <div class="product-options">
                    <button v-for="candidate in item.response.after_sales_selection.candidates" :key="candidate.application_id" type="button" :disabled="isSending" @click="sendMessage(`售后申请 #${candidate.application_id}`)">
                      <strong>#{{ candidate.application_id }} · {{ candidate.application_type_label }}</strong>
                      <span>{{ candidate.product_name || '整笔订单' }} · {{ candidate.status_label }}</span>
                    </button>
                  </div>
                </section>
              </div>
            </article>
            <div v-if="isSending" class="typing-indicator" role="status"><span></span><span></span><span></span>正在处理你的问题</div>
          </div>

          <div class="composer-area">
            <div class="quick-prompts" aria-label="快捷问题"><button v-for="prompt in quickPrompts" :key="prompt" type="button" :disabled="isSending || isCreatingConversation" @click="sendMessage(prompt)">{{ prompt }}</button></div>
            <form class="composer" @submit.prevent="sendMessage()">
              <textarea v-model="messageInput" :disabled="isSending || isCreatingConversation" rows="2" placeholder="例如：订单号 202607240001 的耳机损坏了，想申请退货" @keydown.enter.exact.prevent="sendMessage()"></textarea>
              <button class="send-button" type="submit" :disabled="isSending || isCreatingConversation || !messageInput.trim()">{{ isSending ? "处理中" : "发送" }}</button>
            </form>
            <p class="composer-note">Enter 发送；Shift + Enter 换行。涉及写操作时，系统会先要求明确确认。</p>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>
