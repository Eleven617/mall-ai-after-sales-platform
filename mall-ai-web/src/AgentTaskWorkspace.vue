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
</script>

<template>
  <section class="agent-task-workspace" aria-label="电商 Agent 任务工作台">
    <header>
      <div>
        <p class="eyebrow">AGENT RUNTIME</p>
        <h2>复杂订单与售后任务</h2>
        <p>提交一个目标后，Agent 会在受控 Skill 范围内形成计划、核验事实并给出行动卡。</p>
      </div>
      <button class="text-button" type="button" :disabled="isCreating || !!busyTaskRef" @click="refresh">刷新</button>
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

    <p v-if="error" class="agent-task-error" role="alert">{{ error }}</p>
    <p v-else-if="!visibleTasks.length" class="agent-task-note">当前会话还没有开放任务。普通咨询仍可使用下方客服对话。</p>

    <ol v-else class="agent-task-list">
      <li v-for="task in visibleTasks" :key="task.task_ref" class="agent-task-card">
        <div class="agent-task-heading">
          <div>
            <p class="card-caption">计划第 {{ task.plan_version }} 版</p>
            <h3>{{ task.goal }}</h3>
          </div>
          <span class="return-status">{{ task.status }}</span>
        </div>

        <ol v-if="task.plan_nodes.length" class="agent-plan-list">
          <li v-for="node in task.plan_nodes" :key="`${node.node_label}-${node.goal}`">
            <strong>{{ node.node_label }}</strong><span>{{ node.goal }}</span><em>{{ node.status }}</em>
          </li>
        </ol>

        <ul v-if="task.artifacts.length" class="agent-artifact-list">
          <li v-for="artifact in task.artifacts" :key="`${artifact.kind}-${artifact.summary}`">
            <strong>{{ artifact.kind }}</strong><span>{{ artifact.summary }}</span><em>{{ artifact.factuality }}</em>
          </li>
        </ul>

        <p v-if="task.open_question" class="agent-open-question">{{ task.open_question }}</p>
        <p v-if="task.outcome" class="agent-outcome">{{ task.outcome }}</p>
        <p v-if="task.execution_summary" class="agent-execution-summary">{{ task.execution_summary }}</p>
        <p v-if="task.context_summary" class="agent-context-summary">
          上下文包 v{{ task.context_summary.version }}：
          {{ task.context_summary.token_estimate_before }} → {{ task.context_summary.token_estimate_after }} tokens 估算，
          关键事实引用保留 {{ Math.round(task.context_summary.fact_reference_retention * 100) }}%。
        </p>

        <section v-if="task.action" class="agent-action-card">
          <p class="card-caption">待确认行动</p>
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

        <p v-if="task.limitation_codes.length" class="agent-limitation">当前限制：{{ task.limitation_codes.join('、') }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.agent-task-workspace { margin: 18px 0; padding: 20px; border: 1px solid #d6e4ff; border-radius: 16px; background: #f7faff; }
.agent-task-workspace header, .agent-task-heading, .agent-action-buttons { display: flex; gap: 14px; justify-content: space-between; align-items: flex-start; }
.agent-task-workspace h2, .agent-task-workspace h3 { margin: 2px 0 8px; color: #17396a; }
.agent-task-workspace header p:not(.eyebrow) { margin: 0; color: #536579; line-height: 1.55; }
.agent-task-form, .agent-continue-form { display: grid; gap: 8px; margin-top: 16px; }
.agent-task-form textarea, .agent-continue-form input { width: 100%; box-sizing: border-box; border: 1px solid #c7d7ee; border-radius: 10px; padding: 10px; font: inherit; }
.agent-task-form .primary-button { justify-self: start; }
.agent-task-list, .agent-plan-list, .agent-artifact-list { display: grid; gap: 10px; padding: 0; list-style: none; }
.agent-task-list { margin: 16px 0 0; }
.agent-task-card { padding: 16px; border-radius: 12px; background: #fff; border: 1px solid #dfe8f5; }
.agent-plan-list li, .agent-artifact-list li { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: baseline; font-size: .92rem; }
.agent-plan-list strong, .agent-artifact-list strong { color: #365a8e; }
.agent-plan-list em, .agent-artifact-list em { color: #6d7d91; font-style: normal; }
.agent-open-question, .agent-outcome, .agent-limitation { padding: 9px 10px; border-radius: 8px; background: #f6f8fb; color: #384b61; }
.agent-execution-summary, .agent-context-summary, .agent-task-note { color: #6a7785; font-size: .88rem; }
.agent-action-card { padding: 12px; border: 1px solid #f0d194; border-radius: 10px; background: #fff9ec; }
.agent-action-card p { margin: 6px 0; }
.agent-task-error { color: #b42318; }
@media (max-width: 700px) { .agent-task-workspace header, .agent-task-heading, .agent-action-buttons { flex-direction: column; } .agent-plan-list li, .agent-artifact-list li { grid-template-columns: 1fr; gap: 2px; } }
</style>
