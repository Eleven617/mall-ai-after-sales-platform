export interface VerifiedFactField {
  label: string;
  value: string;
}

export interface VerifiedFactCard {
  source: "order_service" | "logistics_service" | "inventory_service" | "rag_search";
  title: string;
  fields: VerifiedFactField[];
}

export interface TaskPublicState {
  task_status: "active" | "paused" | "none";
  task_label?: string | null;
  task_hint?: string | null;
}

/** Safe public projection of a Mall v3 Agent Runtime task. */
export type AgentTaskStatus =
  | "created"
  | "planning"
  | "executing"
  | "replanning"
  | "waiting_for_user"
  | "waiting_for_async_task"
  | "ready_to_commit"
  | "committing"
  | "completed"
  | "failed"
  | "blocked"
  | "cancelled";

export interface AgentTaskPlanNodeView {
  node_label: string;
  goal: string;
  status: "pending" | "running" | "completed" | "blocked" | "skipped";
}

export interface AgentTaskArtifactView {
  kind: string;
  summary: string;
  source_skill: string;
  factuality: "verified" | "derived" | "proposal" | "unavailable";
}

export interface AgentTaskActionView {
  action_skill: string;
  expected_effect: string;
  user_explanation: string;
  confirmation_status:
    | "not_required"
    | "awaiting_confirmation"
    | "confirmed"
    | "withdrawn"
    | "expired"
    | "committed"
    | "blocked"
    | "unknown";
}

/** Aggregate-only Context Pack metrics; no prompt, source reference or raw fact is exposed. */
export interface AgentTaskContextView {
  version: number;
  token_estimate_before: number;
  token_estimate_after: number;
  fact_reference_retention: number;
}

export interface AgentTaskPublicView {
  /** Opaque public reference; internal task IDs and action arguments stay server-side. */
  task_ref: string;
  goal: string;
  status: AgentTaskStatus;
  plan_version: number;
  plan_nodes: AgentTaskPlanNodeView[];
  artifacts: AgentTaskArtifactView[];
  open_question?: string | null;
  action?: AgentTaskActionView | null;
  outcome?: string | null;
  limitation_codes: string[];
  execution_summary?: string | null;
  context_summary?: AgentTaskContextView | null;
}

export type DiagnosisCategory =
  | "delivery_in_transit"
  | "delivery_exception"
  | "order_state_review"
  | "facts_incomplete"
  | "policy_consultation"
  | "policy_insufficient"
  | "tool_failure"
  | "needs_order_identifier";

export type DiagnosisEvidenceStatus =
  | "complete"
  | "partial"
  | "insufficient"
  | "unavailable";

export type DiagnosisNextStep =
  | "continue_after_sales"
  | "contact_human"
  | "retry_diagnosis"
  | "provide_order_sn";

export interface DiagnosisHandoff {
  summary: string;
}

export interface DiagnosisResult {
  category: DiagnosisCategory;
  evidence_status: DiagnosisEvidenceStatus;
  allowed_next_steps: DiagnosisNextStep[];
  handoff?: DiagnosisHandoff | null;
}

export type AfterSalesApplicationType =
  | "cancel_refund"
  | "return_refund"
  | "exchange"
  | "repair";

export type AfterSalesCompletedAction = "create" | "cancel" | "modify";

export type AfterSalesApplicationStatus =
  | "pending_review"
  | "accepted"
  | "completed"
  | "rejected"
  | "cancelled"
  | "unknown";

export type AfterSalesFulfillmentStatus =
  | "not_started"
  | "processing"
  | "succeeded"
  | "failed"
  | "manual_required"
  | "unknown";

export interface AfterSalesProductOption {
  product_name: string;
  product_attr?: string | null;
}

export interface AfterSalesDraftView {
  draft_id: string;
  status: "collecting_information";
  missing_fields: Array<"application_type" | "order_sn" | "product" | "reason">;
  goal?: "eligibility" | "apply" | null;
  application_type?: AfterSalesApplicationType | null;
  application_type_label?: string | null;
  order_sn?: string | null;
  product_options: AfterSalesProductOption[];
}

export interface AfterSalesProposalView {
  application_type: AfterSalesApplicationType;
  application_type_label: string;
  order_sn: string;
  product_name: string;
  product_attr?: string | null;
  reason: string;
  description: string;
  status: "awaiting_confirmation";
}

export interface AfterSalesEligibilityView {
  order_sn: string;
  application_type: AfterSalesApplicationType;
  application_type_label: string;
  order_status: string;
  eligible: boolean;
  requires_product_selection: boolean;
  decision: "eligible_to_apply" | "not_eligible" | "needs_product_selection";
  message: string;
  product_name?: string | null;
  product_attr?: string | null;
}

export interface AfterSalesApplicationView {
  application_id: number;
  order_sn: string;
  application_type: AfterSalesApplicationType;
  application_type_label: string;
  product_name?: string | null;
  product_attr?: string | null;
  reason: string;
  description: string;
  status: AfterSalesApplicationStatus;
  status_label: string;
  created_at?: number | null;
  updated_at?: number | null;
  handling_note?: string | null;
  fulfillment_status: AfterSalesFulfillmentStatus;
  fulfillment_status_label: string;
  fulfillment_note?: string | null;
  can_cancel: boolean;
  can_modify: boolean;
  can_supplement: boolean;
}

export interface AfterSalesPendingActionView {
  action: "cancel" | "modify";
  application_id: number;
  application_type_label: string;
  status: "awaiting_confirmation";
  impact_summary: string;
  reason?: string | null;
  description?: string | null;
}

export interface AfterSalesApplicationCandidateView {
  application_id: number;
  application_type_label: string;
  status_label: string;
  product_name?: string | null;
  created_at?: number | null;
}

export interface AfterSalesSelectionView {
  purpose: "status" | "cancel" | "modify" | "follow_up";
  candidates: AfterSalesApplicationCandidateView[];
}

export interface CustomerServiceResponse {
  answer: string;
  verified_facts?: VerifiedFactCard[] | null;
  after_sales_draft?: AfterSalesDraftView | null;
  after_sales_proposal?: AfterSalesProposalView | null;
  after_sales_eligibility?: AfterSalesEligibilityView | null;
  submitted_after_sales_application?: AfterSalesApplicationView | null;
  after_sales_completed_action?: AfterSalesCompletedAction | null;
  after_sales_pending_action?: AfterSalesPendingActionView | null;
  after_sales_selection?: AfterSalesSelectionView | null;
  after_sales_applications?: AfterSalesApplicationView[] | null;
  diagnosis?: DiagnosisResult | null;
  task?: TaskPublicState | null;
  response_ref?: string | null;
}

export type CustomerFeedbackReasonCode =
  | "factual_mismatch"
  | "policy_not_supported"
  | "unclear_explanation"
  | "response_too_slow"
  | "tool_unavailable"
  | "other";

export interface CustomerFeedbackRequest {
  response_ref: string;
  helpful: boolean;
  reason_code: CustomerFeedbackReasonCode;
  consent: true;
}

export interface CustomerFeedbackView {
  feedback_id: string;
  response_ref: string;
  helpful: boolean;
  reason_code: CustomerFeedbackReasonCode;
  review_status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
}

export type ServiceCaseState =
  | "QUEUED"
  | "CLAIMED"
  | "AWAITING_CUSTOMER_INFORMATION"
  | "IN_REVIEW"
  | "RESOLVED"
  | "REOPENED"
  | "CLOSED"
  | "CANCELLED";

export interface CustomerServiceCaseView {
  case_id: string;
  category: DiagnosisCategory;
  state: ServiceCaseState;
  state_version: number;
  public_status: string;
  customer_information_required: boolean;
  required_information_type?: "problem_description" | "purchase_context" | null;
  can_cancel: boolean;
  can_reopen: boolean;
  last_public_message?: string | null;
  updated_at?: string | null;
}

export interface CustomerServiceCaseTimelineEntry {
  action_type: string;
  result_code: string;
  public_message: string;
  created_at?: string | null;
}

export interface CustomerServiceCaseInformationRequest {
  expected_version: number;
  idempotency_key: string;
  information_type: "problem_description" | "purchase_context";
  information: string;
}

export interface CustomerServiceCaseCancelRequest {
  expected_version: number;
  idempotency_key: string;
}

export interface CustomerServiceCaseReopenRequest {
  expected_version: number;
  idempotency_key: string;
  reason: string;
}

export interface CustomerServiceRequest {
  session_id: string;
  message: string;
}

export interface CustomerConversationSummary {
  conversation_id: string;
  title: string;
  message_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CustomerConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  public_response?: CustomerServiceResponse | null;
  created_at?: string | null;
}

export interface CustomerConversationDetail {
  conversation: CustomerConversationSummary;
  messages: CustomerConversationMessage[];
}

export interface MemberProfile {
  member_id: number;
  username: string;
}

export interface CustomerLoginRequest {
  username: string;
  password: string;
}

export interface CustomerLoginResponse {
  authorization: string;
  member: MemberProfile;
}

export interface OperatorProfile {
  username: string;
  capabilities: Array<"operations_analysis" | "case_review">;
}

export interface OperatorLoginRequest {
  username: string;
  password: string;
}

export interface OperatorLoginResponse {
  authorization: string;
  operator: OperatorProfile;
}

export interface ServiceProcessorProfile {
  username: string;
  capabilities: Array<"service_case_handling">;
}

export interface ServiceProcessorLoginRequest {
  username: string;
  password: string;
}

export interface ServiceProcessorLoginResponse {
  authorization: string;
  processor: ServiceProcessorProfile;
}

export interface ServiceProcessorCaseView {
  case_id: string;
  queue_ref: "logistics_review" | "policy_review" | "general_after_sales";
  diagnosis_category: DiagnosisCategory;
  priority: "low" | "normal" | "high";
  state: ServiceCaseState;
  state_version: number;
  assigned_to_me: boolean;
  public_status: string;
  customer_information_type?: "problem_description" | "purchase_context" | null;
  customer_information?: string | null;
  last_public_message?: string | null;
  updated_at?: string | null;
}

export interface ServiceProcessorClaimRequest {
  expected_version: number;
  idempotency_key: string;
}

export interface ServiceProcessorActionRequest {
  expected_version: number;
  idempotency_key: string;
  action: "request_information" | "start_review" | "resolve" | "close";
  information_type?: "problem_description" | "purchase_context";
  public_message?: string;
  internal_note?: string;
}

export interface OperationsCase {
  case_id: string;
  source_flow: "customer_diagnosis";
  diagnosis_category: DiagnosisCategory;
  evidence_status: DiagnosisEvidenceStatus;
  handoff_reason: "tool_failure" | "insufficient_evidence" | "manual_review";
  requires_human_review: true;
  case_status: "OPEN" | "CLOSED";
  schema_version: "1";
  created_at?: string | null;
  updated_at?: string | null;
}

export interface OperationsMetrics {
  window_days: 7 | 30;
  after_sales_by_status: Record<string, number>;
  reason_counts: Record<string, number>;
  outbox_by_status: Record<string, number>;
  delivery_by_status: Record<string, number>;
  handoff_overview?: HandoffOverview | null;
}

export interface HandoffCategorySummary {
  category: string;
  count: number;
  percentage: number;
}

export interface HandoffOverview {
  window_days: 7 | 30;
  window_start: string;
  window_end: string;
  total_unique_handoffs: number;
  categories: HandoffCategorySummary[];
}

export type OperationsRiskCode =
  | "pending_review_pressure"
  | "delivery_backlog"
  | "outbox_backlog"
  | "data_insufficient"
  | "none";

export interface OperationsRiskFlag {
  code: OperationsRiskCode;
  severity: "low" | "medium" | "high";
  rationale: string;
}

export interface OperationsAnalysisDraft {
  summary: string;
  risk_flags: OperationsRiskFlag[];
  recommended_human_attention: string[];
  limitations: string[];
}

export interface OperationsAnalysisResponse {
  case: OperationsCase;
  metrics: OperationsMetrics;
  draft: OperationsAnalysisDraft;
}

export interface QualityDeveloperProfile {
  username: string;
  capabilities: Array<"quality_evaluation">;
}

export interface QualityDeveloperLoginRequest {
  username: string;
  password: string;
}

export interface QualityDeveloperLoginResponse {
  authorization: string;
  developer: QualityDeveloperProfile;
}

export interface QualityFailureAnalysis {
  failure_type: string;
  explanation: string;
  candidate_regression_case: string;
  recommended_fix_area: string;
  requires_human_approval: true;
}

export type QualityEvaluationMode = "contract_mock" | "live_model_synthetic";

export interface QualityTrajectory {
  tool_sequence: Array<
    "order_service"
    | "logistics_service"
    | "inventory_service"
    | "rag_search"
    | "synthetic_unapproved_tool"
  >;
  node_sequence: string[];
  step_count: number;
  terminal_events: string[];
}

export interface QualityEvaluationCase {
  case_id: string;
  target_agent: "customer_diagnosis" | "operations_analysis";
  status: "PASSED" | "FAILED";
  expected: string;
  actual: string;
  violations: string[];
  trajectory?: QualityTrajectory | null;
  failure_analysis?: QualityFailureAnalysis | null;
  review_status: "PENDING" | "APPROVED" | "REJECTED";
  expected_rejection_detected?: boolean;
  environment_blocked?: boolean;
}

export interface QualityEvaluationRun {
  run_id: string;
  suite_version: string;
  total: number;
  passed: number;
  failed: number;
  execution_mode: QualityEvaluationMode;
  cases: QualityEvaluationCase[];
  ran_at: string;
  ai_failure_analysis_requested: boolean;
  environment_blocked?: boolean;
  profile_id?: string;
  profile_version?: string;
  run_manifest?: QualityRunManifest | null;
}

export interface QualityRunManifest {
  manifest_version: "1";
  correlation_ref: string;
  role: "quality_evaluation";
  skill_catalog_version: string;
  profile_id: string;
  profile_version: string;
  prompt_version: string;
  rag_profile_version: string;
  tool_schema_version: string;
  fixture_hash: string;
  execution_mode: QualityEvaluationMode;
  duration_ms: number;
  provider_total_tokens?: number | null;
  result_kind: "passed" | "failed" | "environment_blocked";
  error_category?: string | null;
  replay_of_ref?: string | null;
  replayable: boolean;
  replay_reason_code: string;
}

export interface QualityReplayStatus {
  run_id: string;
  replayable: boolean;
  reason_code: string;
}

export interface EvaluationProfile {
  profile_id: string;
  version: string;
  execution_mode: QualityEvaluationMode;
  model_ref: "none" | "configured_deepseek";
  prompt_version: string;
  rag_profile_version: string;
  tool_schema_version: string;
  max_model_calls: number;
  max_tool_calls: number;
  timeout_seconds: number;
  max_attempts: number;
  active: boolean;
}

export interface QualityLocalMetric {
  name: string;
  total: number;
  succeeded: number;
  failed: number;
  p50_ms?: number | null;
  p95_ms?: number | null;
}

export interface FeedbackCandidate {
  candidate_id: string;
  feedback_id: string;
  target_agent: "customer_diagnosis" | "operations_analysis";
  sanitized_scenario: string;
  review_status: "PENDING" | "APPROVED" | "REJECTED";
  eval_case_id?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}
