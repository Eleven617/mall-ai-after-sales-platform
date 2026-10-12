<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  confirmAgentTaskAction,
  amendAgentTaskAction,
  CustomerServiceApiError,
  getAgentTasks,
} from "./api";
import type { AgentTaskPublicView } from "./types";

const props = defineProps<{
  authorization: string;
  sessionId: string;
  refreshKey: number;
  sending: boolean;
}>();

const tasks = ref<AgentTaskPublicView[]>([]);
const error = ref("");
const busyTaskRef = ref("");
let generation = 0;
const editTypeByTask = ref<Record<string, "cancel_refund" | "return_refund" | "exchange" | "repair">>({});

const visibleTasks = computed(() => tasks.value.filter((task) => task.status !== "cancelled"));

watch(
  () => [props.authorization, props.sessionId, props.refreshKey],
  () => { tasks.value = []; error.value = ""; void refresh(); },
  { immediate: true },
);

async function refresh(): Promise<void> {
  const current = ++generation;
  if (!props.authorization || !props.sessionId) return;
  try {
    const result = await getAgentTasks(props.sessionId, props.authorization);
    if (current !== generation) return;
    tasks.value = result;
    error.value = "";
  } catch (reason) {
    if (current === generation) error.value = messageFor(reason, "处理详情暂时无法读取。");
  }
}

async function act(task: AgentTaskPublicView, confirmation: "confirm" | "withdraw"): Promise<void> {
  if (busyTaskRef.value || props.sending) return;
  busyTaskRef.value = task.task_ref;
  const current = generation;
  error.value = "";
  try {
    if (!task.action) return;
    const result = await confirmAgentTaskAction(task.task_ref, confirmation, props.authorization, task.action.proposal_ref, task.action.revision);
    if (current === generation) upsert(result);
  } catch (reason) {
    if (current === generation) error.value = messageFor(reason, "行动未完成，请刷新后重试。");
  } finally {
    busyTaskRef.value = "";
  }
}

async function amend(task: AgentTaskPublicView): Promise<void> {
  if (!task.action || busyTaskRef.value || props.sending) return;
  const applicationType = editTypeByTask.value[task.task_ref] || task.action.application_type || "return_refund";
  const current = generation;
  busyTaskRef.value = task.task_ref;
  error.value = "";
  try {
    const result = await amendAgentTaskAction(task.task_ref, {
      proposal_ref: task.action.proposal_ref,
      revision: task.action.revision,
      application_type: applicationType,
    }, props.authorization);
    if (current === generation) upsert(result);
  } catch (reason) {
    if (current === generation) error.value = messageFor(reason, "方案已更新，请刷新后重新确认。");
  } finally {
    busyTaskRef.value = "";
  }
}

function upsert(task: AgentTaskPublicView): void {
  const index = tasks.value.findIndex((item) => item.task_ref === task.task_ref);
  if (index < 0) {
    tasks.value = [task, ...tasks.value];
    return;
  }
  const updated = [...tasks.value];
  updated[index] = task;
  tasks.value = updated;
}

function messageFor(reason: unknown, fallback: string): string {
  return reason instanceof CustomerServiceApiError ? reason.message : fallback;
}

async function reconcile(task: AgentTaskPublicView): Promise<void> {
  const current=generation;
  try { const response=await fetch('/api/human-handoffs/'+encodeURIComponent(task.task_ref)+'/result',{headers:{Authorization:props.authorization}});
    if(!response.ok)throw new Error();
    const value=await response.json();if(current===generation)upsert(value);
  } catch { if(current===generation)error.value='交接结果仍待确认，请稍后查询；无需重新建案。'; }
}
const handoffReasons: Record<string,string>={human_preference:'希望人工帮助',intent_misunderstood:'意图未理解',repeated_questions:'重复追问',answer_or_evidence_insufficient:'回答或证据不足',tool_or_system_error:'工具或系统异常',capability_or_permission_limit:'能力或权限限制',business_dispute:'业务争议',delay_or_complex_process:'等待或流程复杂',unspecified:'未填写'};
const handoffTopics: Record<string,string>={general:'一般咨询',unknown:'未知',policy:'政策咨询',logistics:'物流',refund:'退款',return:'退货',exchange:'换货',repair:'维修',application_follow_up:'申请进度'};

function statusLabel(status: AgentTaskPublicView["status"]): string {
  return {
    created: "已创建",
    planning: "正在理解目标",
    executing: "正在调查事实",
    replanning: "正在根据新事实调整方案",
    waiting_for_user: "等待你补充信息",
    waiting_for_async_task: "等待业务查询完成",
    waiting_human: "已登记，等待人工处理",
    ready_to_commit: "方案已准备，等待确认",
    committing: "正在提交",
    completed: "已完成",
    blocked: "当前无法继续",
    failed: "处理失败",
    cancelled: "已取消",
  }[status];
}

function statusTone(status: AgentTaskPublicView["status"]): string {
  if (["completed"].includes(status)) return "success";
  if (["blocked", "failed"].includes(status)) return "danger";
  if (["waiting_for_user", "waiting_for_async_task", "ready_to_commit"].includes(status)) return "warning";
  return "agent";
}

function nodeStatusLabel(status: AgentTaskPublicView["plan_nodes"][number]["status"]): string {
  return { pending: "待处理", running: "进行中", completed: "已完成", blocked: "阻塞", skipped: "未触发" }[status];
}

function artifactKindLabel(kind: string): string {
  return { fact: "事实", evidence: "证据", proposal: "方案", limitation: "限制" }[kind] || "任务产物";
}

function artifactFactualityLabel(value: AgentTaskPublicView["artifacts"][number]["factuality"]): string {
  return { verified: "已核验", derived: "推导", proposal: "方案", unavailable: "不可用" }[value];
}

function limitationLabel(code: string): string {
  return {
    insufficient_evidence: "政策证据不足；草案不代表资格或处理成功，确认时由 Java 重新核验",
    MODEL_UNAVAILABLE: "模型服务暂不可用",
    EVIDENCE_INSUFFICIENT: "当前证据不足，需要补充信息",
    TOOL_UNAVAILABLE: "必要的查询服务暂不可用",
    HUMAN_REVIEW_REQUIRED: "需要人工协同处理",
    CONFIRMATION_REQUIRED: "提交前需要你的明确确认",
  }[code] || "当前任务存在服务端限制";
}

function actionStatusLabel(status: NonNullable<AgentTaskPublicView["action"]>["confirmation_status"]): string {
  return {
    not_required: "无需确认",
    awaiting_confirmation: "等待确认",
    confirmed: "已确认",
    withdrawn: "已撤回",
    expired: "已过期",
    committed: "已提交",
    blocked: "暂时阻塞",
    unknown: "状态待核实",
    superseded: "已被新版本替代",
  }[status];
}
</script>

<template>
  <section v-if="visibleTasks.length || error" class="agent-task-workspace" aria-label="当前会话处理详情">
    <header class="agent-workspace-header">
      <div><h2>处理进度与方案</h2><p>需要补充信息时，直接在对话框回复即可。</p></div>
      <button class="secondary-button" type="button" :disabled="sending || !!busyTaskRef" @click="refresh">刷新状态</button>
    </header>
    <p v-if="error" class="error-state" role="alert">{{ error }}</p>

    <ol class="agent-task-list">
      <li v-for="task in visibleTasks" :key="task.task_ref" class="agent-task-card">
        <div class="agent-task-heading">
          <div>
            <p class="card-caption">处理事项 · 方案第 {{ task.plan_version }} 版</p>
            <h3>{{ task.goal }}</h3>
          </div>
          <span class="status-badge" :class="statusTone(task.status)">{{ statusLabel(task.status) }}</span>
        </div>

        <ol v-if="task.plan_nodes.length" class="timeline agent-plan-list">
          <li v-for="node in task.plan_nodes" :key="`${node.node_label}-${node.goal}`" class="timeline-item" :class="node.status">
            <span class="timeline-dot" aria-hidden="true"></span>
            <span class="timeline-copy"><strong>{{ node.node_label }} · {{ nodeStatusLabel(node.status) }}</strong><span>{{ node.goal }}</span></span>
          </li>
        </ol>

        <ul v-if="task.artifacts.length" class="agent-artifact-list">
          <li v-for="artifact in task.artifacts" :key="`${artifact.kind}-${artifact.summary}`">
            <div><strong>{{ artifactKindLabel(artifact.kind) }}</strong><span>{{ artifact.summary }}</span></div><em class="status-badge" :class="artifact.factuality === 'verified' ? 'success' : artifact.factuality === 'unavailable' ? 'danger' : artifact.factuality === 'proposal' ? 'warning' : 'agent'">{{ artifactFactualityLabel(artifact.factuality) }}</em>
          </li>
        </ul>

        <p v-if="task.open_question" class="agent-open-question">{{ task.open_question }}</p>
        <p v-if="task.outcome" class="agent-outcome">{{ task.outcome }}</p>
        <p v-if="task.handoff_topic">交接业务：{{handoffTopics[task.handoff_topic] || '一般咨询'}}；客户选择原因：{{handoffReasons[task.handoff_reason || 'unspecified']}}。只提交结构化事项背景，不提交原始聊天。</p>
        <p v-if="task.handoff_problem">将保存的问题预览：{{task.handoff_problem.customer_goal}}；{{task.handoff_problem.unresolved_question || '暂未提供具体问题，仍可转人工'}}。这是客户待核实的问题描述。</p>
        <details v-if="task.handoff_context_preview?.length"><summary>交接使用的安全背景</summary><p v-for="(text,i) in task.handoff_context_preview" :key="i">{{text}}</p><p>确认后异步生成问题摘要，人工仍需核实业务事实。</p></details>
        <p v-if="task.execution_summary" class="agent-execution-summary">{{ task.execution_summary }}</p>

        <section v-if="task.action" class="agent-action-card">
          <button v-if="task.action.action_skill==='open_human_case' && task.action.confirmation_status==='unknown'" class="secondary-button" @click="reconcile(task)">查询原交接结果</button>
          <div class="agent-action-heading"><p class="card-caption">行动方案</p><span class="status-badge" :class="task.action.confirmation_status === 'awaiting_confirmation' ? 'warning' : task.action.confirmation_status === 'committed' ? 'success' : 'agent'">{{ actionStatusLabel(task.action.confirmation_status) }}</span></div>
          <strong>{{ task.action.expected_effect }}</strong>
          <p>{{ task.action.user_explanation }}</p>
          <p v-if="task.action.application_type_label" class="agent-action-detail">当前类型：{{ task.action.application_type_label }} · 版本 {{ task.action.revision }} · 确认前不会写入商城</p>
          <p v-if="task.limitation_codes.includes('insufficient_evidence')" class="agent-policy-boundary">政策证据不足：此草案仅表达你的申请意向，不代表政策支持或资格通过；确认后仍由 Java 重新核验。</p>
          <ul v-if="task.action.evidence_summaries.length" class="agent-action-evidence"><li v-for="item in task.action.evidence_summaries" :key="item">{{ item }}</li></ul>
          <div v-if="task.action.confirmation_status === 'awaiting_confirmation'" class="agent-action-buttons">
            <select v-if="task.action.application_type" v-model="editTypeByTask[task.task_ref]" aria-label="修改售后类型">
              <option value="cancel_refund">取消退款</option><option value="return_refund">退货退款</option><option value="exchange">换货</option><option value="repair">维修</option>
            </select>
            <button v-if="task.action.application_type" class="secondary-button" type="button" :disabled="sending || !!busyTaskRef" @click="amend(task)">修改方案</button>
            <button class="primary-button" type="button" :disabled="sending || !!busyTaskRef" @click="act(task, 'confirm')">确认后提交</button>
            <button class="secondary-button" type="button" :disabled="sending || !!busyTaskRef" @click="act(task, 'withdraw')">暂不提交</button>
          </div>
        </section>

        <p v-if="task.limitation_codes.length" class="agent-limitation">处理边界：{{ task.limitation_codes.map(limitationLabel).join('；') }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.agent-task-workspace { margin: 18px 0; padding: 20px; border: 1px solid #ddd6fe; border-radius: var(--radius-md); background: linear-gradient(145deg, #fafaff, #f5f3ff); }
.agent-workspace-header, .agent-task-heading, .agent-action-buttons, .agent-action-heading { display: flex; gap: 14px; justify-content: space-between; align-items: flex-start; }
.agent-task-workspace h2, .agent-task-workspace h3 { margin: 2px 0 8px; color: #312e81; }
.agent-task-workspace header p:not(.eyebrow) { margin: 0; color: var(--ink-600); line-height: 1.55; }
.agent-task-form, .agent-continue-form { display: grid; gap: 8px; margin-top: 16px; }
.agent-task-form label, .agent-continue-form label { color: var(--ink-600); font-size: 12px; font-weight: 750; }
.agent-task-form textarea, .agent-continue-form input { width: 100%; box-sizing: border-box; border: 1px solid #c4b5fd; border-radius: var(--radius-sm); padding: 10px; background: var(--surface); font: inherit; }
.agent-task-form .primary-button { justify-self: start; }
.agent-task-list, .agent-artifact-list { display: grid; gap: 12px; padding: 0; list-style: none; }
.agent-task-list { margin: 16px 0 0; }
.agent-task-card { display: grid; gap: 13px; padding: 16px; border-radius: var(--radius-sm); background: var(--surface); border: 1px solid #e2e8f0; box-shadow: 0 4px 14px rgb(76 29 149 / 4%); }
.agent-plan-list { margin: 0; padding: 2px 0 0; }
.agent-artifact-list { margin: 0; }
.agent-artifact-list li { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; padding: 10px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface-soft); font-size: .92rem; }
.agent-artifact-list li > div { display: grid; gap: 3px; min-width: 0; }
.agent-artifact-list strong { color: #365a8e; font-size: 12px; }
.agent-artifact-list span { color: var(--ink-600); line-height: 1.45; }
.agent-open-question, .agent-outcome, .agent-limitation, .agent-policy-boundary { margin: 0; padding: 10px 11px; border-radius: 8px; background: #f6f8fb; color: #384b61; line-height: 1.5; }
.agent-policy-boundary { border-left: 3px solid #f59e0b; background: #fffbeb; }
.agent-open-question { border-left: 3px solid #f59e0b; background: #fffbeb; }
.agent-outcome { border-left: 3px solid #34d399; background: #f0fdf4; }
.agent-execution-summary, .agent-context-summary, .agent-task-note { color: var(--ink-600); font-size: .88rem; line-height: 1.55; }
.agent-action-card { display: grid; gap: 7px; padding: 14px; border: 1px solid #bbf7d0; border-radius: var(--radius-sm); background: #f0fdf4; }
.agent-action-card p { margin: 0; line-height: 1.55; }
.agent-action-card > strong { color: #166534; }
.agent-action-buttons { justify-content: flex-start; margin-top: 4px; }
.agent-context-details { border-top: 1px solid var(--line); padding-top: 9px; color: var(--ink-600); }
.agent-context-details summary { cursor: pointer; color: #475569; font-size: 12px; font-weight: 750; }
.agent-task-error { margin: 14px 0 0; }
@media (max-width: 700px) { .agent-workspace-header, .agent-task-heading, .agent-action-buttons { flex-direction: column; } .agent-action-buttons { align-items: stretch; } .agent-action-buttons button { width: 100%; } .agent-artifact-list li { flex-direction: column; } }
</style>
