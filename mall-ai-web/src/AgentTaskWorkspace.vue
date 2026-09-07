<script setup lang="ts">
import { computed, ref, watch } from "vue";

import {
  confirmAgentTaskAction,
  continueAgentTask,
  createAgentTask,
  CustomerServiceApiError,
  getAgentTasks,
} from "./api";
import type { AgentTaskPublicView } from "./types";

const props = defineProps<{
  authorization: string;
  sessionId: string;
}>();

const goal = ref("");
const tasks = ref<AgentTaskPublicView[]>([]);
const continuationByTask = ref<Record<string, string>>({});
const error = ref("");
const busyTaskRef = ref("");
const isCreating = ref(false);

const visibleTasks = computed(() => tasks.value.filter((task) => task.status !== "cancelled"));

watch(
  () => [props.authorization, props.sessionId],
  () => {
    void refresh();
  },
  { immediate: true },
);

async function refresh(): Promise<void> {
  if (!props.authorization || !props.sessionId || isCreating.value || busyTaskRef.value) {
    return;
  }
  try {
    tasks.value = await getAgentTasks(props.sessionId, props.authorization);
    error.value = "";
  } catch (reason) {
    error.value = messageFor(reason, "Agent 任务暂时无法读取。");
  }
}

async function createTask(): Promise<void> {
  const currentGoal = goal.value.trim();
  if (!currentGoal || !props.authorization || isCreating.value) {
    return;
  }
  isCreating.value = true;
  error.value = "";
  try {
    const task = await createAgentTask(
      { session_id: props.sessionId, goal: currentGoal },
      props.authorization,
    );
    upsert(task);
    goal.value = "";
  } catch (reason) {
    error.value = messageFor(reason, "Agent 任务未创建。");
  } finally {
    isCreating.value = false;
  }
}

async function continueTask(task: AgentTaskPublicView): Promise<void> {
  const message = (continuationByTask.value[task.task_ref] || "").trim();
  if (!message || busyTaskRef.value) {
    return;
  }
  busyTaskRef.value = task.task_ref;
  error.value = "";
  try {
    const updated = await continueAgentTask(task.task_ref, message, props.authorization);
    upsert(updated);
    continuationByTask.value = { ...continuationByTask.value, [task.task_ref]: "" };
  } catch (reason) {
    error.value = messageFor(reason, "任务未继续，请稍后重试。");
  } finally {
    busyTaskRef.value = "";
  }
}

async function act(task: AgentTaskPublicView, confirmation: "confirm" | "withdraw"): Promise<void> {
  if (busyTaskRef.value) return;
  busyTaskRef.value = task.task_ref;
  error.value = "";
  try {
    upsert(await confirmAgentTaskAction(task.task_ref, confirmation, props.authorization));
  } catch (reason) {
    error.value = messageFor(reason, "行动未完成，请刷新后重试。");
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

function statusLabel(status: AgentTaskPublicView["status"]): string {
  return {
    created: "已创建",
    planning: "正在理解目标",
    executing: "正在调查事实",
    replanning: "正在根据新事实调整方案",
    waiting_for_user: "等待你补充信息",
    waiting_for_async_task: "等待业务查询完成",
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
  }[status];
}
</script>

<template>
  <section class="agent-task-workspace" aria-label="电商 Agent 任务工作台">
    <header class="agent-workspace-header">
      <div>
        <p class="eyebrow">OPEN TASK AGENT</p>
        <h2>开放任务工作台</h2>
        <p>围绕你的目标调查订单、物流、库存和政策事实，并在需要写入前给出确认卡。</p>
      </div>
      <button class="secondary-button" type="button" :disabled="isCreating || !!busyTaskRef" @click="refresh">刷新任务</button>
    </header>

    <form class="agent-task-form" @submit.prevent="createTask">
      <label for="agent-task-goal">任务目标</label>
      <textarea
        id="agent-task-goal"
        v-model="goal"
        maxlength="1000"
        rows="3"
        placeholder="例如：订单延误且即将出行，核验物流和可用方案；如需写入请先给我确认卡。"
      />
      <button class="primary-button" type="submit" :disabled="isCreating || !goal.trim()">
        {{ isCreating ? "正在形成计划" : "创建 Agent 任务" }}
      </button>
    </form>

    <p v-if="error" class="error-state agent-task-error" role="alert">{{ error }}</p>
    <p v-else-if="!visibleTasks.length" class="empty-state agent-task-note">当前会话还没有开放任务。普通咨询仍可使用下方客服对话；需要多步调查时可从这里开始。</p>

    <ol v-else class="agent-task-list">
      <li v-for="task in visibleTasks" :key="task.task_ref" class="agent-task-card">
        <div class="agent-task-heading">
          <div>
            <p class="card-caption">开放目标 · 计划第 {{ task.plan_version }} 版</p>
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
        <p v-if="task.execution_summary" class="agent-execution-summary">{{ task.execution_summary }}</p>
        <details v-if="task.context_summary" class="agent-context-details">
          <summary>处理摘要</summary>
          <p class="agent-context-summary">上下文摘要 v{{ task.context_summary.version }}：保留关键事实引用 {{ Math.round(task.context_summary.fact_reference_retention * 100) }}%，上下文规模从 {{ task.context_summary.token_estimate_before }} 调整为 {{ task.context_summary.token_estimate_after }} 的估算值。</p>
        </details>

        <section v-if="task.action" class="agent-action-card">
          <div class="agent-action-heading"><p class="card-caption">行动方案</p><span class="status-badge" :class="task.action.confirmation_status === 'awaiting_confirmation' ? 'warning' : task.action.confirmation_status === 'committed' ? 'success' : 'agent'">{{ actionStatusLabel(task.action.confirmation_status) }}</span></div>
          <strong>{{ task.action.expected_effect }}</strong>
          <p>{{ task.action.user_explanation }}</p>
          <div v-if="task.action.confirmation_status === 'awaiting_confirmation'" class="agent-action-buttons">
            <button class="primary-button" type="button" :disabled="busyTaskRef === task.task_ref" @click="act(task, 'confirm')">确认后提交</button>
            <button class="secondary-button" type="button" :disabled="busyTaskRef === task.task_ref" @click="act(task, 'withdraw')">暂不提交</button>
          </div>
        </section>

        <form v-if="task.status === 'waiting_for_user'" class="agent-continue-form" @submit.prevent="continueTask(task)">
          <label :for="`continue-${task.task_ref}`">补充信息</label>
          <input :id="`continue-${task.task_ref}`" v-model="continuationByTask[task.task_ref]" maxlength="1000" placeholder="按任务问题补充必要信息" />
          <button class="secondary-button" type="submit" :disabled="busyTaskRef === task.task_ref || !(continuationByTask[task.task_ref] || '').trim()">继续任务</button>
        </form>

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
.agent-open-question, .agent-outcome, .agent-limitation { margin: 0; padding: 10px 11px; border-radius: 8px; background: #f6f8fb; color: #384b61; line-height: 1.5; }
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
