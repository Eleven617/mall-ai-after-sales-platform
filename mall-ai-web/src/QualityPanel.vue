<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  CustomerServiceApiError,
  getQualityFeedbackCandidates,
  getQualityMetrics,
  getQualityProfiles,
  getQualityReplayStatus,
  getCurrentQualityDeveloper,
  getLatestQualityEvaluation,
  loginQualityDeveloper,
  replayQualityEvaluation,
  reviewQualityFeedbackCandidate,
  reviewQualityEvaluationCase,
  runQualityEvaluation,
} from "./api";
import type {
  EvaluationProfile,
  FeedbackCandidate,
  QualityDeveloperProfile,
  QualityEvaluationMode,
  QualityEvaluationCase,
  QualityEvaluationRun,
  QualityLocalMetric,
  QualityReplayStatus,
} from "./types";

const TOKEN_KEY = "mall-ai-web:quality-developer-token";

const authorization = ref(window.sessionStorage.getItem(TOKEN_KEY) || "");
const developer = ref<QualityDeveloperProfile | null>(null);
const username = ref("");
const password = ref("");
const loginError = ref("");
const runError = ref("");
const isLoggingIn = ref(false);
const isRunning = ref(false);
const isReplaying = ref(false);
const isRestoring = ref(false);
const reviewCaseId = ref("");
const reviewFeedbackCandidateId = ref("");
const executionMode = ref<QualityEvaluationMode>("contract_mock");
const enableAiFailureAnalysis = ref(false);
const evaluation = ref<QualityEvaluationRun | null>(null);
const replayStatus = ref<QualityReplayStatus | null>(null);
const profiles = ref<EvaluationProfile[]>([]);
const metrics = ref<QualityLocalMetric[]>([]);
const feedbackCandidates = ref<FeedbackCandidate[]>([]);

const resultSummary = computed(() => {
  if (!evaluation.value) return "尚未运行";
  return `${evaluation.value.passed} 通过 / ${evaluation.value.failed} 失败`;
});

const selectedSuiteLabel = computed(() => (
  executionMode.value === "contract_mock" ? "quality-agent.v2" : "live-model-synthetic.v1"
));

const selectedModeDescription = computed(() => (
  executionMode.value === "contract_mock"
    ? "零模型调用：固定合成工具和聚合数据，适合每次 CI 与本地回归。"
    : "真实模型 + 合成输入与模拟工具：只手动运行，会产生模型成本和网络延迟，不访问客户或业务数据。"
));

watch(authorization, (value) => {
  if (value.trim()) {
    window.sessionStorage.setItem(TOKEN_KEY, value.trim());
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
});

void restoreDeveloperSession();

async function login(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    loginError.value = "请输入开发者用户名和密码。";
    return;
  }
  isLoggingIn.value = true;
  loginError.value = "";
  try {
    const result = await loginQualityDeveloper({
      username: username.value.trim(),
      password: password.value,
    });
    authorization.value = result.authorization;
    developer.value = result.developer;
    password.value = "";
    await loadLatestEvaluation();
    await loadQualitySupportData();
  } catch (error) {
    loginError.value = messageFor(error, "开发者登录未完成，请稍后重试。");
  } finally {
    isLoggingIn.value = false;
  }
}

async function restoreDeveloperSession(): Promise<void> {
  if (!authorization.value) return;
  isRestoring.value = true;
  try {
    developer.value = await getCurrentQualityDeveloper(authorization.value);
    await loadLatestEvaluation();
    await loadQualitySupportData();
  } catch {
    logout();
  } finally {
    isRestoring.value = false;
  }
}

async function loadLatestEvaluation(): Promise<void> {
  if (!authorization.value) return;
  try {
    evaluation.value = await getLatestQualityEvaluation(authorization.value);
  } catch (error) {
    if (error instanceof CustomerServiceApiError && error.status === 404) {
      evaluation.value = null;
      replayStatus.value = null;
      return;
    }
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      logout();
      return;
    }
    runError.value = messageFor(error, "无法读取最近一次质量评测。");
  }
  await loadReplayStatus();
}

async function loadQualitySupportData(): Promise<void> {
  if (!authorization.value) return;
  try {
    const [loadedProfiles, loadedMetrics, loadedCandidates] = await Promise.all([
      getQualityProfiles(authorization.value),
      getQualityMetrics(authorization.value),
      getQualityFeedbackCandidates(authorization.value),
    ]);
    profiles.value = loadedProfiles;
    metrics.value = loadedMetrics;
    feedbackCandidates.value = loadedCandidates;
  } catch (error) {
    runError.value = messageFor(error, "无法读取质量治理的安全投影。");
  }
}

async function loadReplayStatus(): Promise<void> {
  if (!authorization.value || !evaluation.value) {
    replayStatus.value = null;
    return;
  }
  try {
    replayStatus.value = await getQualityReplayStatus(evaluation.value.run_id, authorization.value);
  } catch (error) {
    replayStatus.value = null;
    runError.value = messageFor(error, "无法读取评测安全回放状态。");
  }
}

async function runEvaluation(): Promise<void> {
  if (!authorization.value || isRunning.value) return;
  isRunning.value = true;
  runError.value = "";
  try {
    evaluation.value = await runQualityEvaluation(
      authorization.value,
      executionMode.value,
      enableAiFailureAnalysis.value,
    );
    await loadReplayStatus();
    await loadQualitySupportData();
  } catch (error) {
    runError.value = messageFor(error, "质量评测未完成，请稍后重试。");
    if (error instanceof CustomerServiceApiError && error.status === 401) {
      logout();
    }
  } finally {
    isRunning.value = false;
  }
}

async function replayEvaluation(): Promise<void> {
  if (!authorization.value || !evaluation.value || !replayStatus.value?.replayable || isReplaying.value) return;
  isReplaying.value = true;
  runError.value = "";
  try {
    evaluation.value = await replayQualityEvaluation(evaluation.value.run_id, authorization.value);
    await loadReplayStatus();
    await loadQualitySupportData();
  } catch (error) {
    runError.value = messageFor(error, "安全回放未完成，请稍后重试。");
  } finally {
    isReplaying.value = false;
  }
}

async function reviewCase(
  item: QualityEvaluationCase,
  reviewStatus: "APPROVED" | "REJECTED",
): Promise<void> {
  if (!authorization.value || !evaluation.value || reviewCaseId.value) return;
  reviewCaseId.value = item.case_id;
  try {
    evaluation.value = await reviewQualityEvaluationCase(
      evaluation.value.run_id,
      item.case_id,
      reviewStatus,
      authorization.value,
    );
  } catch (error) {
    runError.value = messageFor(error, "人工审批状态未更新。");
  } finally {
    reviewCaseId.value = "";
  }
}

async function reviewFeedbackCandidate(
  candidate: FeedbackCandidate,
  reviewStatus: "APPROVED" | "REJECTED",
): Promise<void> {
  if (!authorization.value || reviewFeedbackCandidateId.value) return;
  reviewFeedbackCandidateId.value = candidate.candidate_id;
  try {
    const updated = await reviewQualityFeedbackCandidate(
      candidate.candidate_id,
      reviewStatus,
      authorization.value,
    );
    feedbackCandidates.value = feedbackCandidates.value.map((item) => (
      item.candidate_id === updated.candidate_id ? updated : item
    ));
  } catch (error) {
    runError.value = messageFor(error, "反馈候选审核状态未更新。");
  } finally {
    reviewFeedbackCandidateId.value = "";
  }
}

function logout(): void {
  authorization.value = "";
  developer.value = null;
  evaluation.value = null;
  replayStatus.value = null;
  profiles.value = [];
  metrics.value = [];
  feedbackCandidates.value = [];
  loginError.value = "";
  runError.value = "";
}

function messageFor(error: unknown, fallback: string): string {
  return error instanceof CustomerServiceApiError ? error.message : fallback;
}

function targetLabel(target: QualityEvaluationCase["target_agent"]): string {
  return target === "customer_diagnosis" ? "统一售后 Agent（只读调查）" : "运营分析 Agent";
}

function replayReasonLabel(status: QualityReplayStatus | null): string {
  if (!status) return "暂无安全回放状态";
  const labels: Record<string, string> = {
    synthetic_contract_fixture_retained: "可用：固定合成夹具已保留",
    live_model_requires_explicit_evaluation: "不可用：实时模型评测必须显式重新发起",
    runtime_fixture_not_retained: "不可用：运行时夹具未保留",
    profile_not_available: "不可用：原评测 Profile 已不存在",
    fixture_version_mismatch: "不可用：夹具或 Profile 版本不一致",
  };
  return labels[status.reason_code] || "不可用：安全回放条件不满足";
}
</script>

<template>
  <section class="quality-panel" aria-label="AI 质量评测">
    <div v-if="isRestoring" class="quality-muted">正在验证开发者身份…</div>

    <form v-else-if="!developer" class="quality-login" @submit.prevent="login">
      <div>
        <p class="quality-eyebrow">DEVELOPER ONLY</p>
        <h2>AI 质量评测</h2>
        <p>仅运行版本化合成案例；不会读取客户聊天、订单、Token、RAG 原文或生产 Trace。</p>
      </div>
      <label>
        开发者账号
        <input v-model="username" autocomplete="username" maxlength="64" />
      </label>
      <label>
        密码
        <input v-model="password" type="password" autocomplete="current-password" maxlength="128" />
      </label>
      <p v-if="loginError" class="quality-error" role="alert">{{ loginError }}</p>
      <button type="submit" :disabled="isLoggingIn">
        {{ isLoggingIn ? "正在登录…" : "开发者登录" }}
      </button>
    </form>

    <div v-else class="quality-workspace">
      <header class="quality-workspace-header">
        <div>
          <p class="quality-eyebrow">ISOLATED EVALUATION</p>
          <h2>AI 质量评测 Agent</h2>
          <p>已验证开发者：{{ developer.username }}。评测只产生内存中的脱敏结果，不执行业务写入。</p>
        </div>
        <button class="quality-link-button" type="button" @click="logout">退出开发者身份</button>
      </header>

      <section class="quality-run-control">
        <div>
          <strong>评测套件：{{ evaluation?.suite_version || selectedSuiteLabel }}</strong>
          <span>结果：{{ resultSummary }}</span>
        </div>
        <label class="quality-select">
          执行档位
          <select v-model="executionMode" :disabled="isRunning">
            <option value="contract_mock">contract_mock（默认、CI）</option>
            <option value="live_model_synthetic">live_model_synthetic（手动）</option>
          </select>
        </label>
        <label class="quality-checkbox">
          <input v-model="enableAiFailureAnalysis" type="checkbox" />
          失败时请求 AI 归因建议
        </label>
        <p>{{ selectedModeDescription }}</p>
        <p>失败归因只会在确定性合同实际失败后调用一次额外模型，始终只给建议且需要人工审批。</p>
        <button type="button" :disabled="isRunning" @click="runEvaluation">
          {{ isRunning ? "正在重跑合成评测…" : "重跑评测" }}
        </button>
        <div v-if="evaluation" class="quality-replay-control">
          <span>安全回放：{{ replayReasonLabel(replayStatus) }}</span>
          <button
            v-if="replayStatus?.replayable"
            type="button"
            :disabled="isRunning || isReplaying"
            @click="replayEvaluation"
          >{{ isReplaying ? "正在安全回放…" : "回放固定合成夹具" }}</button>
        </div>
        <p v-if="runError" class="quality-error" role="alert">{{ runError }}</p>
      </section>

      <section v-if="evaluation" class="quality-results" aria-live="polite">
        <header class="quality-results-header">
          <div>
            <h3>最近一次结果</h3>
            <p>档位：{{ evaluation.execution_mode }} · 共 {{ evaluation.total }} 条 · {{ evaluation.passed }} 通过 · {{ evaluation.failed }} 失败</p>
          </div>
          <span>运行时间：{{ new Date(evaluation.ran_at).toLocaleString() }}</span>
        </header>

        <section v-if="evaluation.run_manifest" class="quality-manifest">
          <h4>RunManifest（安全元数据）</h4>
          <p>Profile：{{ evaluation.run_manifest.profile_id }}@{{ evaluation.run_manifest.profile_version }} · Prompt：{{ evaluation.run_manifest.prompt_version }}</p>
          <p>RAG：{{ evaluation.run_manifest.rag_profile_version }} · Tool Schema：{{ evaluation.run_manifest.tool_schema_version }}</p>
          <p>夹具指纹：{{ evaluation.run_manifest.fixture_hash.slice(0, 16) }}… · 结果：{{ evaluation.run_manifest.result_kind }} · {{ evaluation.run_manifest.duration_ms }} ms</p>
          <p>这里不展示客户消息、订单号、Token、RAG 原文或生产 Trace。</p>
        </section>

        <article v-for="item in evaluation.cases" :key="item.case_id" class="quality-case">
          <header>
            <div>
              <strong>{{ item.case_id }}</strong>
              <span>{{ targetLabel(item.target_agent) }}</span>
            </div>
            <span :class="['quality-status', item.status.toLowerCase()]">{{ item.status }}</span>
          </header>
          <p><b>预期：</b>{{ item.expected }}</p>
          <p><b>实际安全投影：</b>{{ item.actual }}</p>
          <p v-if="item.violations.length"><b>合同代码：</b>{{ item.violations.join("、") }}</p>
          <p v-if="item.trajectory"><b>合成轨迹：</b>{{ item.trajectory.tool_sequence.join(" → ") || "无工具调用" }} · {{ item.trajectory.step_count }} 步 · {{ item.trajectory.terminal_events.join("、") || "无终态" }}</p>
          <p v-if="item.expected_rejection_detected" class="quality-note">攻击性合成样本已被确定性边界拒绝；这不是业务写入，也不包含真实数据。</p>
          <p v-if="item.environment_blocked" class="quality-error">模型服务不可用：本次结果不能解释为模型质量结论。</p>
          <div v-if="item.failure_analysis" class="quality-analysis">
            <b>AI 归因建议（需人工审批）</b>
            <p>{{ item.failure_analysis.explanation }}</p>
            <p>候选回归题：{{ item.failure_analysis.candidate_regression_case }}</p>
            <p>建议检查：{{ item.failure_analysis.recommended_fix_area }}</p>
          </div>
          <footer>
            <span>人工审批：{{ item.review_status }}</span>
            <div>
              <button
                type="button"
                :disabled="!!reviewCaseId"
                @click="reviewCase(item, 'APPROVED')"
              >认可结果</button>
              <button
                type="button"
                :disabled="!!reviewCaseId"
                @click="reviewCase(item, 'REJECTED')"
              >标记需复核</button>
            </div>
          </footer>
        </article>
      </section>

      <section class="quality-support-grid" aria-label="质量治理安全投影">
        <article class="quality-support-card">
          <h3>版本化 Profile</h3>
          <p>仅用于离线合成评测，不是线上自动模型路由。</p>
          <ul v-if="profiles.length">
            <li v-for="profile in profiles" :key="profile.profile_id">
              <b>{{ profile.profile_id }}@{{ profile.version }}</b>
              <span>{{ profile.execution_mode }} · 模型调用上限 {{ profile.max_model_calls }} · 工具调用上限 {{ profile.max_tool_calls }}</span>
            </li>
          </ul>
          <p v-else class="quality-muted">暂未读取到 Profile。</p>
        </article>

        <article class="quality-support-card">
          <h3>本地指标</h3>
          <p>仅为当前本地进程测量，不代表生产 QPS、SLA 或真实用户表现。</p>
          <ul v-if="metrics.length">
            <li v-for="metric in metrics" :key="metric.name">
              <b>{{ metric.name }}</b>
              <span>{{ metric.succeeded }}/{{ metric.total }} 成功 · p50 {{ metric.p50_ms ?? "—" }} ms · p95 {{ metric.p95_ms ?? "—" }} ms</span>
            </li>
          </ul>
          <p v-else class="quality-muted">当前尚无可显示的本地指标。</p>
        </article>

        <article class="quality-support-card quality-feedback-candidates">
          <h3>脱敏反馈候选</h3>
          <p>候选必须由人工审核；不会自动进入模型、训练、Prompt 或业务写入。</p>
          <ul v-if="feedbackCandidates.length">
            <li v-for="candidate in feedbackCandidates" :key="candidate.candidate_id">
              <div>
                <b>{{ candidate.target_agent === "customer_diagnosis" ? "统一售后 Agent" : "运营分析 Agent" }}</b>
                <span>{{ candidate.sanitized_scenario }}</span>
                <small>状态：{{ candidate.review_status }}{{ candidate.eval_case_id ? ` · EvalCase：${candidate.eval_case_id}` : "" }}</small>
              </div>
              <div v-if="candidate.review_status === 'PENDING'" class="quality-inline-actions">
                <button type="button" :disabled="!!reviewFeedbackCandidateId" @click="reviewFeedbackCandidate(candidate, 'APPROVED')">批准入集</button>
                <button type="button" :disabled="!!reviewFeedbackCandidateId" @click="reviewFeedbackCandidate(candidate, 'REJECTED')">拒绝</button>
              </div>
            </li>
          </ul>
          <p v-else class="quality-muted">暂无脱敏反馈候选。</p>
        </article>
      </section>
    </div>
  </section>
</template>

<style scoped>
.quality-panel { padding: 28px; color: #1e293b; }
.quality-login, .quality-workspace { display: grid; gap: 18px; max-width: 980px; margin: 0 auto; }
.quality-login { max-width: 440px; padding: 28px; border: 1px solid #dbe5ee; border-radius: 16px; background: #fff; }
.quality-login label { display: grid; gap: 7px; font-size: 13px; font-weight: 700; }
.quality-login input { min-height: 40px; padding: 0 10px; border: 1px solid #cbd5e1; border-radius: 8px; }
.quality-panel button { min-height: 38px; padding: 0 14px; border: 0; border-radius: 8px; background: #0f766e; color: #fff; font-weight: 700; cursor: pointer; }
.quality-panel button:disabled { cursor: wait; opacity: .6; }
.quality-eyebrow { margin: 0; color: #0f766e; font-size: 11px; font-weight: 800; letter-spacing: .09em; }
.quality-login h2, .quality-workspace h2, .quality-results h3 { margin: 4px 0 8px; }
.quality-login p, .quality-workspace p { margin: 0; color: #475569; line-height: 1.6; }
.quality-workspace-header, .quality-results-header, .quality-case header, .quality-case footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.quality-workspace-header { padding-bottom: 16px; border-bottom: 1px solid #e2e8f0; }
.quality-link-button { background: transparent !important; color: #0f766e !important; }
.quality-run-control { display: grid; gap: 10px; padding: 18px; border: 1px solid #cfe7e3; border-radius: 12px; background: #f0fdfa; }
.quality-run-control > div { display: flex; gap: 18px; flex-wrap: wrap; }
.quality-checkbox { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; }
.quality-checkbox input { width: 16px; height: 16px; }
.quality-select { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; }
.quality-select select { min-height: 34px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; color: #1e293b; padding: 0 8px; }
.quality-run-control button { width: fit-content; }
.quality-replay-control { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 13px; color: #334155; }
.quality-results { display: grid; gap: 12px; }
.quality-results-header { align-items: flex-end; }
.quality-results-header p { font-size: 13px; }
.quality-results-header > span { color: #64748b; font-size: 12px; }
.quality-case { display: grid; gap: 9px; padding: 16px; border: 1px solid #dbe5ee; border-radius: 12px; background: #fff; }
.quality-case header strong { display: block; font-size: 14px; }
.quality-case header div > span { color: #64748b; font-size: 12px; }
.quality-case p { font-size: 13px; }
.quality-status { padding: 4px 8px; border-radius: 999px; font-size: 11px; font-weight: 800; }
.quality-status.passed { color: #166534; background: #dcfce7; }
.quality-status.failed { color: #b91c1c; background: #fee2e2; }
.quality-case footer { padding-top: 8px; border-top: 1px solid #eef2f7; color: #64748b; font-size: 12px; }
.quality-case footer div { display: flex; gap: 8px; }
.quality-case footer button { min-height: 30px; background: #334155; font-size: 12px; }
.quality-analysis { padding: 12px; border-left: 3px solid #f59e0b; background: #fffbeb; font-size: 13px; }
.quality-analysis p { margin: 5px 0 0; }
.quality-manifest { display: grid; gap: 4px; padding: 14px 16px; border: 1px solid #bfdbfe; border-radius: 12px; background: #eff6ff; font-size: 12px; color: #334155; }
.quality-manifest h4, .quality-manifest p { margin: 0; }
.quality-support-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.quality-support-card { display: grid; gap: 9px; padding: 16px; border: 1px solid #dbe5ee; border-radius: 12px; background: #fff; }
.quality-support-card h3, .quality-support-card p { margin: 0; }
.quality-support-card > p { color: #64748b; font-size: 12px; line-height: 1.55; }
.quality-support-card ul { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.quality-support-card li { display: grid; gap: 4px; padding-top: 9px; border-top: 1px solid #eef2f7; font-size: 12px; }
.quality-support-card li:first-child { padding-top: 0; border-top: 0; }
.quality-support-card li b, .quality-support-card li span, .quality-support-card li small { display: block; }
.quality-support-card li span, .quality-support-card li small { color: #64748b; line-height: 1.45; }
.quality-inline-actions { display: flex; gap: 7px; margin-top: 3px; }
.quality-inline-actions button { min-height: 30px; background: #334155; font-size: 12px; }
.quality-error { color: #b91c1c !important; font-size: 13px; }
.quality-note { color: #0f766e !important; }
.quality-muted { padding: 28px; color: #64748b; text-align: center; }
@media (max-width: 900px) { .quality-support-grid { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .quality-panel { padding: 18px; } .quality-workspace-header, .quality-results-header, .quality-case header, .quality-case footer { align-items: flex-start; flex-direction: column; } }
</style>
