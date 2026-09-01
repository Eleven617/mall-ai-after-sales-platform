<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  actOnServiceProcessorCase,
  claimServiceProcessorCase,
  CustomerServiceApiError,
  getCurrentServiceProcessor,
  getServiceProcessorCases,
  loginServiceProcessor,
} from "./api";
import type {
  ServiceProcessorCaseView,
  ServiceProcessorProfile,
} from "./types";

const TOKEN_KEY = "mall-ai-web:service-processor-token";
const PROFILE_KEY = "mall-ai-web:service-processor-profile";
const token = ref(readSessionValue(TOKEN_KEY));
const processor = ref<ServiceProcessorProfile | null>(readProfile());
const username = ref("");
const password = ref("");
const loginError = ref("");
const casesError = ref("");
const isLoggingIn = ref(false);
const isLoading = ref(false);
const actionInProgress = ref("");
const cases = ref<ServiceProcessorCaseView[]>([]);
const selectedCaseId = ref("");
const publicMessage = ref("");
const internalNote = ref("");
const informationType = ref<"problem_description" | "purchase_context">("problem_description");

const processorState = computed(() =>
  processor.value ? `已授权：${processor.value.username}` : "未登录",
);
const selectedCase = computed(
  () => cases.value.find((item) => item.case_id === selectedCaseId.value) || null,
);

watch(token, (value) => {
  if (value.trim()) window.sessionStorage.setItem(TOKEN_KEY, value.trim());
  else window.sessionStorage.removeItem(TOKEN_KEY);
});
watch(processor, (value) => {
  if (value) window.sessionStorage.setItem(PROFILE_KEY, JSON.stringify(value));
  else window.sessionStorage.removeItem(PROFILE_KEY);
});

void restoreProcessor();

async function login(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    loginError.value = "请输入人工处理人员账号和密码。";
    return;
  }
  isLoggingIn.value = true;
  loginError.value = "";
  try {
    const result = await loginServiceProcessor({ username: username.value.trim(), password: password.value });
    token.value = result.authorization;
    processor.value = result.processor;
    password.value = "";
    await loadCases();
  } catch (error) {
    loginError.value = messageFor(error, "人工处理人员登录未完成，请稍后重试。");
  } finally {
    isLoggingIn.value = false;
  }
}

async function restoreProcessor(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization) return;
  try {
    processor.value = await getCurrentServiceProcessor(authorization);
    await loadCases();
  } catch {
    logout();
  }
}

function logout(): void {
  token.value = "";
  processor.value = null;
  cases.value = [];
  selectedCaseId.value = "";
  casesError.value = "";
  publicMessage.value = "";
  internalNote.value = "";
}

async function loadCases(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization) return;
  isLoading.value = true;
  casesError.value = "";
  try {
    const next = await getServiceProcessorCases(authorization);
    cases.value = next;
    if (selectedCaseId.value && !next.some((item) => item.case_id === selectedCaseId.value)) {
      selectedCaseId.value = "";
    }
  } catch (error) {
    casesError.value = messageFor(error, "人工协同案件暂时无法读取，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) logout();
  } finally {
    isLoading.value = false;
  }
}

function selectCase(value: ServiceProcessorCaseView): void {
  selectedCaseId.value = value.case_id;
  publicMessage.value = value.last_public_message || "";
  internalNote.value = "";
}

async function claim(value: ServiceProcessorCaseView): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization || actionInProgress.value) return;
  actionInProgress.value = value.case_id;
  casesError.value = "";
  try {
    const updated = await claimServiceProcessorCase(
      value.case_id,
      { expected_version: value.state_version, idempotency_key: newIdempotencyKey() },
      authorization,
    );
    upsertCase(updated);
    selectCase(updated);
  } catch (error) {
    casesError.value = messageFor(error, "案件领取未完成，请刷新后重试。");
  } finally {
    actionInProgress.value = "";
  }
}

async function perform(action: "request_information" | "start_review" | "resolve" | "close"): Promise<void> {
  const value = selectedCase.value;
  const authorization = authorizationHeader();
  if (!value || !authorization || !value.assigned_to_me || actionInProgress.value) return;
  if (["request_information", "resolve", "close"].includes(action) && !publicMessage.value.trim()) {
    casesError.value = "请填写客户可见的处理说明。";
    return;
  }
  if (action === "request_information" && !publicMessage.value.trim()) return;
  if (action === "close" && !window.confirm("确认结案吗？结案后客户只能看到公开处理结果。")) return;
  actionInProgress.value = value.case_id;
  casesError.value = "";
  try {
    const updated = await actOnServiceProcessorCase(
      value.case_id,
      {
        expected_version: value.state_version,
        idempotency_key: newIdempotencyKey(),
        action,
        information_type: action === "request_information" ? informationType.value : undefined,
        public_message: publicMessage.value.trim() || undefined,
        internal_note: internalNote.value.trim() || undefined,
      },
      authorization,
    );
    upsertCase(updated);
    selectCase(updated);
  } catch (error) {
    casesError.value = messageFor(error, "案件操作未完成，请刷新后重试。");
  } finally {
    actionInProgress.value = "";
  }
}

function upsertCase(value: ServiceProcessorCaseView): void {
  const index = cases.value.findIndex((item) => item.case_id === value.case_id);
  if (index === -1) cases.value = [value, ...cases.value];
  else {
    const next = [...cases.value];
    next[index] = value;
    cases.value = next;
  }
}

function authorizationHeader(): string | undefined {
  const value = token.value.trim();
  if (!value) return undefined;
  return value.startsWith("Bearer ") ? value : `Bearer ${value}`;
}

function readSessionValue(key: string): string { return window.sessionStorage.getItem(key) || ""; }
function readProfile(): ServiceProcessorProfile | null {
  const raw = window.sessionStorage.getItem(PROFILE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<ServiceProcessorProfile>;
    return typeof value.username === "string" && Array.isArray(value.capabilities)
      ? { username: value.username, capabilities: ["service_case_handling"] }
      : null;
  } catch { return null; }
}
function messageFor(error: unknown, fallback: string): string {
  return error instanceof CustomerServiceApiError ? error.message : fallback;
}
function newIdempotencyKey(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replace(/-/g, "");
  let result = "";
  while (result.length < 32) result += Math.random().toString(16).slice(2);
  return result.slice(0, 32).padEnd(32, "0");
}
function stateLabel(value: ServiceProcessorCaseView["state"]): string {
  return {
    QUEUED: "待领取", CLAIMED: "已领取", AWAITING_CUSTOMER_INFORMATION: "等待客户补充",
    IN_REVIEW: "核验中", RESOLVED: "已处理", REOPENED: "重新开启", CLOSED: "已结案", CANCELLED: "已取消",
  }[value];
}
function categoryLabel(value: ServiceProcessorCaseView["diagnosis_category"]): string {
  return {
    delivery_in_transit: "配送处理中", delivery_exception: "配送异常", order_state_review: "订单状态待核实",
    facts_incomplete: "事实未完成", policy_consultation: "政策咨询", policy_insufficient: "政策证据不足",
    tool_failure: "工具暂不可用", needs_order_identifier: "缺少订单号",
  }[value];
}
</script>

<template>
  <section class="processor-panel" aria-label="人工售后协同处理台">
    <div class="processor-heading">
      <div>
        <p class="panel-kicker">HUMAN SERVICE CASES</p>
        <h2>人工售后协同处理台</h2>
        <p>只处理最小化转接案件；不能查看客户完整对话、订单号、支付信息、模型 Trace，也不能修改订单、退款或售后申请。</p>
      </div>
      <span class="status-pill" :class="{ active: processor }"><span class="status-dot"></span>{{ processorState }}</span>
    </div>

    <form v-if="!processor" class="processor-login" @submit.prevent="login">
      <label class="login-field"><span>处理人员用户名</span><input v-model="username" autocomplete="username" /></label>
      <label class="login-field"><span>处理人员密码</span><input v-model="password" type="password" autocomplete="current-password" /></label>
      <button class="primary-button" type="submit" :disabled="isLoggingIn">{{ isLoggingIn ? "验证中" : "处理人员登录" }}</button>
      <p v-if="loginError" class="login-error" role="alert">{{ loginError }}</p>
    </form>

    <div v-else class="processor-workspace">
      <div class="processor-toolbar"><p>领取、补件、核验、处理和结案均由 Java 状态机、版本、幂等、审计与 Outbox 约束。</p><div><button class="secondary-button" type="button" :disabled="isLoading" @click="loadCases">刷新案件</button><button class="secondary-button" type="button" @click="logout">退出登录</button></div></div>
      <p v-if="casesError" class="processor-error">{{ casesError }}</p>
      <p v-else-if="isLoading" class="processor-note">正在读取可领取和本人已领取的最小案件...</p>
      <div v-else-if="cases.length" class="processor-layout">
        <div class="processor-case-list">
          <button v-for="item in cases" :key="item.case_id" class="processor-case-button" :class="{ selected: selectedCase?.case_id === item.case_id }" type="button" @click="selectCase(item)">
            <strong>{{ categoryLabel(item.diagnosis_category) }}</strong><span>{{ item.queue_ref }} · {{ item.priority }}</span><small>{{ stateLabel(item.state) }}{{ item.assigned_to_me ? " · 已分配给我" : "" }}</small>
          </button>
        </div>
        <div v-if="selectedCase" class="processor-detail">
          <section class="processor-card"><p class="card-caption">案件状态</p><h3>{{ categoryLabel(selectedCase.diagnosis_category) }}</h3><dl><div><dt>队列</dt><dd>{{ selectedCase.queue_ref }}</dd></div><div><dt>状态</dt><dd>{{ stateLabel(selectedCase.state) }}</dd></div><div><dt>客户可见状态</dt><dd>{{ selectedCase.public_status }}</dd></div><div v-if="selectedCase.assigned_to_me && selectedCase.customer_information"><dt>客户补充</dt><dd>{{ selectedCase.customer_information }}</dd></div></dl><button v-if="!selectedCase.assigned_to_me && selectedCase.state === 'QUEUED'" class="primary-button" type="button" :disabled="actionInProgress === selectedCase.case_id" @click="claim(selectedCase)">领取案件</button></section>
          <section v-if="selectedCase.assigned_to_me" class="processor-card"><p class="card-caption">受控人工操作</p><label>客户可见说明<textarea v-model="publicMessage" maxlength="500" rows="3" placeholder="客户会看到这段说明；不要填写内部系统或敏感信息"></textarea></label><label>内部备注<textarea v-model="internalNote" maxlength="500" rows="2" placeholder="仅用于审计，不会返回给客户或运营"></textarea></label><label v-if="selectedCase.state === 'CLAIMED' || selectedCase.state === 'IN_REVIEW'">补件类型<select v-model="informationType"><option value="problem_description">问题说明</option><option value="purchase_context">购买/使用背景</option></select></label><div class="processor-actions"><button v-if="selectedCase.state === 'CLAIMED' || selectedCase.state === 'IN_REVIEW'" class="secondary-button" type="button" :disabled="actionInProgress === selectedCase.case_id" @click="perform('request_information')">请求补件</button><button v-if="selectedCase.state === 'CLAIMED' || selectedCase.state === 'REOPENED'" class="secondary-button" type="button" :disabled="actionInProgress === selectedCase.case_id" @click="perform('start_review')">开始核验</button><button v-if="selectedCase.state === 'IN_REVIEW'" class="primary-button" type="button" :disabled="actionInProgress === selectedCase.case_id" @click="perform('resolve')">标记已处理</button><button v-if="selectedCase.state === 'RESOLVED'" class="primary-button" type="button" :disabled="actionInProgress === selectedCase.case_id" @click="perform('close')">结案</button></div></section>
        </div>
        <p v-else class="processor-note">选择一条案件后开始人工处理。</p>
      </div>
      <p v-else class="processor-note">当前没有可领取或已领取的人工协同案件。</p>
    </div>
  </section>
</template>

<style scoped>
.processor-panel { padding: 22px 28px; background: #fff7ed; }.processor-heading, .processor-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; }.processor-heading h2 { margin: 4px 0 8px; color: #9a3412; font-size: 18px; }.processor-heading p:not(.panel-kicker), .processor-toolbar p { max-width: 760px; margin: 0; color: #64748b; font-size: 13px; line-height: 1.55; }.processor-login { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; margin-top: 17px; }.processor-workspace { margin-top: 16px; }.processor-toolbar > div, .processor-actions { display: flex; flex-wrap: wrap; gap: 9px; }.processor-error { margin: 13px 0 0; color: #b91c1c; font-size: 13px; }.processor-note { margin: 14px 0 0; color: #64748b; font-size: 13px; }.processor-layout { display: grid; grid-template-columns: minmax(230px, .7fr) minmax(0, 1.3fr); gap: 16px; margin-top: 16px; }.processor-case-list { display: grid; align-content: start; gap: 8px; max-height: 440px; overflow: auto; }.processor-case-button { display: grid; gap: 4px; padding: 12px; border: 1px solid #fed7aa; border-radius: 10px; color: #334155; background: #fff; text-align: left; }.processor-case-button.selected { border-color: #ea580c; background: #fff7ed; }.processor-case-button strong { color: #9a3412; font-size: 13px; }.processor-case-button span, .processor-case-button small { color: #64748b; font-size: 11px; }.processor-detail { display: grid; gap: 11px; }.processor-card { display: grid; gap: 10px; padding: 14px; border: 1px solid #fed7aa; border-radius: 12px; background: #fff; }.processor-card h3 { margin: 0; color: #9a3412; font-size: 15px; }.processor-card dl { display: grid; gap: 7px; margin: 0; }.processor-card dl div { display: grid; grid-template-columns: 100px 1fr; gap: 9px; font-size: 12px; }.processor-card dt { color: #64748b; }.processor-card dd { margin: 0; color: #1e293b; font-weight: 650; word-break: break-word; }.processor-card label { display: grid; gap: 5px; color: #475569; font-size: 12px; font-weight: 700; }.processor-card textarea, .processor-card select { padding: 8px 9px; border: 1px solid #cbd5e1; border-radius: 7px; color: #1e293b; font: inherit; }.processor-card textarea { resize: vertical; }.processor-card textarea:focus, .processor-card select:focus { border-color: #ea580c; outline: 0; box-shadow: 0 0 0 3px rgb(234 88 12 / 10%); }@media (max-width: 780px) { .processor-panel { padding: 18px; }.processor-heading, .processor-toolbar { align-items: flex-start; flex-direction: column; }.processor-layout { grid-template-columns: 1fr; } }
</style>
