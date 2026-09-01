<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  analyzeOperationsCase,
  CustomerServiceApiError,
  getCurrentOperator,
  getOperationsCases,
  getOperationsHandoffOverview,
  loginOperator,
} from "./api";
import type {
  HandoffOverview,
  OperationsAnalysisResponse,
  OperationsCase,
  OperatorProfile,
} from "./types";

const TOKEN_KEY = "mall-ai-web:operations-token";
const OPERATOR_KEY = "mall-ai-web:operations-profile";
const operatorToken = ref(readSessionValue(TOKEN_KEY));
const operator = ref<OperatorProfile | null>(readOperatorProfile());
const username = ref("");
const password = ref("");
const loginError = ref("");
const isLoggingIn = ref(false);
const isLoadingCases = ref(false);
const casesError = ref("");
const cases = ref<OperationsCase[]>([]);
const selectedCase = ref<OperationsCase | null>(null);
const analysis = ref<OperationsAnalysisResponse | null>(null);
const analysisError = ref("");
const isAnalyzing = ref(false);
const windowDays = ref<7 | 30>(7);
const handoffOverview = ref<HandoffOverview | null>(null);
const isLoadingOverview = ref(false);
const overviewError = ref("");

const operatorState = computed(() =>
  operator.value ? `已授权：${operator.value.username}` : "未登录",
);

watch(operatorToken, (value) => {
  if (value.trim()) {
    window.sessionStorage.setItem(TOKEN_KEY, value.trim());
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
});

watch(operator, (value) => {
  if (value) {
    window.sessionStorage.setItem(OPERATOR_KEY, JSON.stringify(value));
  } else {
    window.sessionStorage.removeItem(OPERATOR_KEY);
  }
});

watch(windowDays, () => {
  analysis.value = null;
  void loadHandoffOverview();
});

void restoreOperator();

async function login(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    loginError.value = "请输入运营账号和密码。";
    return;
  }
  isLoggingIn.value = true;
  loginError.value = "";
  try {
    const result = await loginOperator({
      username: username.value.trim(),
      password: password.value,
    });
    operatorToken.value = result.authorization;
    operator.value = result.operator;
    password.value = "";
    await Promise.all([loadCases(), loadHandoffOverview()]);
  } catch (error) {
    loginError.value = messageFor(error, "运营登录未完成，请稍后重试。");
  } finally {
    isLoggingIn.value = false;
  }
}

function logout(): void {
  operatorToken.value = "";
  operator.value = null;
  cases.value = [];
  selectedCase.value = null;
  analysis.value = null;
  analysisError.value = "";
  handoffOverview.value = null;
  overviewError.value = "";
}

async function restoreOperator(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization) {
    return;
  }
  try {
    operator.value = await getCurrentOperator(authorization);
  } catch {
    logout();
  }
}

async function loadCases(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization) {
    return;
  }
  isLoadingCases.value = true;
  casesError.value = "";
  try {
    cases.value = await getOperationsCases(authorization);
    if (
      selectedCase.value
      && !cases.value.some((item) => item.case_id === selectedCase.value?.case_id)
    ) {
      selectedCase.value = null;
      analysis.value = null;
    }
  } catch (error) {
    casesError.value = messageFor(error, "运营案例暂时无法加载，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      logout();
    }
  } finally {
    isLoadingCases.value = false;
  }
}

async function loadHandoffOverview(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization) {
    return;
  }
  isLoadingOverview.value = true;
  overviewError.value = "";
  try {
    handoffOverview.value = await getOperationsHandoffOverview(
      authorization,
      windowDays.value,
    );
  } catch (error) {
    handoffOverview.value = null;
    overviewError.value = messageFor(error, "转人工概览暂时无法加载，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      logout();
    }
  } finally {
    isLoadingOverview.value = false;
  }
}

function selectCase(value: OperationsCase): void {
  selectedCase.value = value;
  analysis.value = null;
  analysisError.value = "";
}

async function generateAnalysis(): Promise<void> {
  const authorization = authorizationHeader();
  if (!authorization || !selectedCase.value || isAnalyzing.value) {
    return;
  }
  isAnalyzing.value = true;
  analysisError.value = "";
  try {
    analysis.value = await analyzeOperationsCase(
      selectedCase.value.case_id,
      authorization,
      windowDays.value,
    );
    handoffOverview.value = analysis.value.metrics.handoff_overview || handoffOverview.value;
  } catch (error) {
    analysis.value = null;
    analysisError.value = messageFor(error, "运营分析草稿暂不可用，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      logout();
    }
  } finally {
    isAnalyzing.value = false;
  }
}

function authorizationHeader(): string | undefined {
  const token = operatorToken.value.trim();
  if (!token) {
    return undefined;
  }
  return token.startsWith("Bearer ") ? token : `Bearer ${token}`;
}

function readSessionValue(key: string): string {
  return window.sessionStorage.getItem(key) || "";
}

function readOperatorProfile(): OperatorProfile | null {
  const raw = window.sessionStorage.getItem(OPERATOR_KEY);
  if (!raw) {
    return null;
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") {
      return null;
    }
    const data = value as Record<string, unknown>;
    return typeof data.username === "string" && Array.isArray(data.capabilities)
      ? (data as unknown as OperatorProfile)
      : null;
  } catch {
    return null;
  }
}

function messageFor(error: unknown, fallback: string): string {
  return error instanceof CustomerServiceApiError ? error.message : fallback;
}

function formatTime(value?: string | null): string {
  if (!value) {
    return "暂未更新";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "时间不可用"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function categoryLabel(value: OperationsCase["diagnosis_category"]): string {
  return {
    delivery_in_transit: "配送处理中",
    delivery_exception: "配送异常",
    order_state_review: "订单状态待核实",
    facts_incomplete: "订单与物流事实未完成",
    policy_consultation: "政策咨询",
    policy_insufficient: "政策证据不足",
    tool_failure: "业务工具暂不可用",
    needs_order_identifier: "缺少订单号",
  }[value];
}

function overviewCategoryLabel(value: string): string {
  return {
    delivery_in_transit: "配送处理中",
    delivery_exception: "配送异常",
    order_state_review: "订单状态待核实",
    facts_incomplete: "订单与物流事实未完成",
    policy_consultation: "政策咨询",
    policy_insufficient: "政策证据不足",
    tool_failure: "业务工具暂不可用",
    needs_order_identifier: "缺少订单号",
    other_pending_classification: "其他（待人工归类）",
  }[value] || "其他（待人工归类）";
}

function evidenceLabel(value: OperationsCase["evidence_status"]): string {
  return { complete: "证据完整", partial: "证据部分完整", insufficient: "证据不足", unavailable: "证据不可用" }[value];
}

function handoffLabel(value: OperationsCase["handoff_reason"]): string {
  return { tool_failure: "工具故障", insufficient_evidence: "证据不足", manual_review: "需要人工核实" }[value];
}

function metricEntries(values: Record<string, number>): Array<[string, number]> {
  return Object.entries(values);
}
</script>

<template>
  <section class="operations-panel" aria-label="内部售后运营工作台">
    <div class="operations-heading">
      <div>
        <p class="panel-kicker">内部运营</p>
        <h2>售后运营分析工作台</h2>
        <p>仅订单管理员与超级管理员可访问；不展示客户个人信息、原始对话或模型内部记录。</p>
      </div>
      <span class="status-pill" :class="{ active: operator }"><span class="status-dot"></span>{{ operatorState }}</span>
    </div>

    <form v-if="!operator" class="operations-login-form" @submit.prevent="login">
      <label class="login-field"><span>运营用户名</span><input v-model="username" autocomplete="username" /></label>
      <label class="login-field"><span>运营密码</span><input v-model="password" type="password" autocomplete="current-password" /></label>
      <button class="primary-button" type="submit" :disabled="isLoggingIn">{{ isLoggingIn ? "验证中" : "运营登录" }}</button>
      <p v-if="loginError" class="login-error" role="alert">{{ loginError }}</p>
    </form>

    <div v-else class="operations-workspace">
      <div class="operations-toolbar">
        <p>当前仅可读取最小化转接事项和聚合统计；分析草稿不会修改售后、订单或退款。</p>
        <div>
          <label class="overview-window">统计窗口
            <select v-model="windowDays" :disabled="isLoadingOverview || isAnalyzing">
              <option :value="7">最近 7 天</option><option :value="30">最近 30 天</option>
            </select>
          </label>
          <button class="secondary-button" type="button" :disabled="isLoadingCases" @click="loadCases">刷新事项</button>
          <button class="secondary-button" type="button" @click="logout">退出运营登录</button>
        </div>
      </div>
      <p v-if="casesError" class="operations-error">{{ casesError }}</p>
      <p v-else-if="isLoadingCases" class="operations-note">正在读取最小化人工跟进事项...</p>
      <section class="operations-card handoff-overview-card" aria-label="转人工概览">
        <p class="card-caption">转人工概览</p>
        <p v-if="isLoadingOverview" class="operations-note">正在按所选时间窗汇总转人工事项...</p>
        <p v-else-if="overviewError" class="operations-error">{{ overviewError }}</p>
        <template v-else-if="handoffOverview">
          <div class="handoff-overview-heading">
            <div><strong>{{ handoffOverview.total_unique_handoffs }}</strong><span>去重后转人工总数</span></div>
            <p>实际统计窗口：{{ handoffOverview.window_start }} 至 {{ handoffOverview.window_end }}（最近 {{ handoffOverview.window_days }} 天）</p>
          </div>
          <p class="overview-method">统计口径：后端按“会员 + caseKey”去重；次数和百分比均由 Java 聚合计算，模型不参与统计。</p>
          <div class="handoff-category-grid">
            <div v-for="item in handoffOverview.categories" :key="item.category">
              <span>{{ overviewCategoryLabel(item.category) }}</span><strong>{{ item.count }} 次 · {{ item.percentage }}%</strong>
            </div>
          </div>
        </template>
      </section>

      <div v-if="cases.length" class="operations-layout">
        <div class="operations-case-list" aria-label="人工跟进事项">
          <button
            v-for="item in cases"
            :key="item.case_id"
            class="operations-case-button"
            :class="{ selected: selectedCase?.case_id === item.case_id }"
            type="button"
            @click="selectCase(item)"
          >
            <strong>{{ categoryLabel(item.diagnosis_category) }}</strong>
            <span>{{ evidenceLabel(item.evidence_status) }} · {{ handoffLabel(item.handoff_reason) }}</span>
            <small>{{ formatTime(item.created_at) }}</small>
          </button>
        </div>

        <div v-if="selectedCase" class="operations-analysis-area">
          <section class="operations-card">
            <p class="card-caption">最小化转接摘要</p>
            <h3>{{ categoryLabel(selectedCase.diagnosis_category) }}</h3>
            <dl>
              <div><dt>证据状态</dt><dd>{{ evidenceLabel(selectedCase.evidence_status) }}</dd></div>
              <div><dt>转接原因</dt><dd>{{ handoffLabel(selectedCase.handoff_reason) }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ formatTime(selectedCase.created_at) }}</dd></div>
            </dl>
          </section>
          <section class="operations-card">
            <div class="analysis-actions">
              <div>
                <p class="card-caption">受控运营分析</p>
                <p>仅在你点击后读取所选窗口的可信聚合数据，并发起一次结构化模型调用。</p>
              </div>
              <button class="primary-button" type="button" :disabled="isAnalyzing" @click="generateAnalysis">{{ isAnalyzing ? "生成中" : "生成分析草稿" }}</button>
            </div>
            <p v-if="analysisError" class="operations-error">{{ analysisError }}</p>
          </section>

          <section v-if="analysis" class="operations-card analysis-result">
            <p class="card-caption">运营分析草稿</p>
            <h3>摘要</h3><p>{{ analysis.draft.summary }}</p>
            <div v-if="analysis.draft.risk_flags.length">
              <h3>关注项</h3>
              <ul><li v-for="risk in analysis.draft.risk_flags" :key="`${risk.code}-${risk.rationale}`">{{ risk.severity }} · {{ risk.rationale }}</li></ul>
            </div>
            <div v-if="analysis.draft.recommended_human_attention.length">
              <h3>建议人工关注</h3>
              <ul><li v-for="item in analysis.draft.recommended_human_attention" :key="item">{{ item }}</li></ul>
            </div>
            <div v-if="analysis.draft.limitations.length">
              <h3>边界</h3>
              <ul><li v-for="item in analysis.draft.limitations" :key="item">{{ item }}</li></ul>
            </div>
            <h3>本次可信聚合</h3>
            <div class="metric-grid">
              <div><strong>售后状态</strong><span v-for="[key, total] in metricEntries(analysis.metrics.after_sales_by_status)" :key="key">{{ key }}：{{ total }}</span></div>
              <div><strong>规范原因</strong><span v-for="[key, total] in metricEntries(analysis.metrics.reason_counts)" :key="key">{{ key }}：{{ total }}</span></div>
              <div><strong>事件投递</strong><span v-for="[key, total] in metricEntries(analysis.metrics.outbox_by_status)" :key="key">{{ key }}：{{ total }}</span></div>
              <div><strong>消费交付</strong><span v-for="[key, total] in metricEntries(analysis.metrics.delivery_by_status)" :key="key">{{ key }}：{{ total }}</span></div>
            </div>
          </section>
        </div>
        <p v-else class="operations-note">选择一条人工跟进事项后，再决定是否生成分析草稿。</p>
      </div>
      <p v-else-if="!isLoadingCases && !casesError" class="operations-note">当前没有可供分析的人工跟进事项。</p>
    </div>
  </section>
</template>

<style scoped>
.operations-panel { padding: 22px 28px; border-bottom: 1px solid #dbe5ee; background: #f8fbff; }
.operations-heading, .operations-heading-actions, .operations-toolbar, .analysis-actions { display: flex; align-items: center; }
.operations-heading { justify-content: space-between; gap: 18px; }
.operations-heading h2 { margin: 4px 0 8px; color: #1e3a5f; font-size: 18px; }
.operations-heading p:not(.panel-kicker) { max-width: 700px; margin: 0; color: #64748b; font-size: 13px; line-height: 1.55; }
.operations-heading-actions, .operations-toolbar > div { gap: 11px; }
.operations-login-form { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; margin-top: 17px; }
.operations-workspace { margin-top: 16px; }
.operations-toolbar { justify-content: space-between; gap: 14px; }
.operations-toolbar p { margin: 0; color: #64748b; font-size: 13px; }
.overview-window { display: grid; gap: 4px; color: #475569; font-size: 11px; font-weight: 700; }
.overview-window select { min-width: 94px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; color: #334155; }
.operations-error { margin: 13px 0 0; color: #b91c1c; font-size: 13px; }
.operations-note { margin: 14px 0 0; color: #64748b; font-size: 13px; }
.operations-layout { display: grid; grid-template-columns: minmax(220px, 0.65fr) minmax(0, 1.35fr); gap: 16px; margin-top: 16px; }
.operations-case-list { display: grid; align-content: start; gap: 8px; max-height: 390px; overflow: auto; }
.operations-case-button { display: grid; gap: 4px; padding: 12px; border: 1px solid #dbe5ee; border-radius: 10px; color: #334155; background: #fff; text-align: left; }
.operations-case-button.selected { border-color: #0f766e; background: #f0fdfa; }
.operations-case-button strong { color: #1e3a5f; font-size: 13px; }
.operations-case-button span, .operations-case-button small { color: #64748b; font-size: 11px; }
.operations-analysis-area { display: grid; gap: 11px; }
.operations-card { padding: 14px; border: 1px solid #dbe5ee; border-radius: 12px; background: #fff; }
.operations-card h3 { margin: 6px 0 9px; color: #1e3a5f; font-size: 14px; }
.operations-card p { color: #475569; font-size: 13px; line-height: 1.6; }
.operations-card dl { display: grid; gap: 7px; margin: 0; }
.operations-card dl div { display: grid; grid-template-columns: 86px 1fr; gap: 9px; font-size: 12px; }
.operations-card dt { color: #64748b; }
.operations-card dd { margin: 0; color: #1e293b; font-weight: 650; }
.handoff-overview-card { display: grid; gap: 8px; margin-top: 15px; }
.handoff-overview-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.handoff-overview-heading > div { display: grid; gap: 2px; }
.handoff-overview-heading strong { color: #0f766e; font-size: 28px; line-height: 1; }
.handoff-overview-heading span, .handoff-overview-heading p, .overview-method { color: #64748b; font-size: 12px; }
.handoff-overview-heading p, .overview-method { margin: 0; }
.handoff-category-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }
.handoff-category-grid div { display: grid; gap: 3px; padding: 8px; border-radius: 8px; background: #f1f5f9; }
.handoff-category-grid span { color: #64748b; font-size: 11px; }
.handoff-category-grid strong { color: #334155; font-size: 12px; }
.analysis-actions { align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.analysis-actions p { max-width: 440px; margin: 3px 0 0; }
.analysis-actions label { display: grid; gap: 5px; color: #475569; font-size: 12px; font-weight: 700; }
.analysis-actions select { padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; }
.analysis-result ul { display: grid; gap: 5px; margin: 0 0 13px; padding-left: 19px; color: #475569; font-size: 13px; line-height: 1.5; }
.metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.metric-grid div { display: grid; gap: 4px; padding: 9px; border-radius: 8px; background: #f8fafc; color: #475569; font-size: 12px; }
.metric-grid strong { color: #334155; }
@media (max-width: 780px) { .operations-panel { padding: 18px; } .operations-heading, .operations-toolbar { align-items: flex-start; flex-direction: column; } .operations-layout { grid-template-columns: 1fr; } .metric-grid, .handoff-category-grid { grid-template-columns: 1fr; } }
</style>
