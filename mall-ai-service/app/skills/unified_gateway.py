"""统一 Skill 入口，兼容工具名仅在网关内部映射，业务实现不变。"""
from app.skills.commerce_gateway import SafeCommerceSkillGateway


class UnifiedSkillGateway(SafeCommerceSkillGateway):
    def reconcile(self, key, *, authorization, member_id, task_ref):
        from app.skills.commerce_gateway import _require_customer_context, SkillObservation, _reference
        from app.services.mall_client import get_after_sales_submission_status, MallApiClientError
        _require_customer_context(authorization, member_id)
        try:
            status, application = get_after_sales_submission_status(key, authorization)
        except MallApiClientError:
            status, application = "unknown", None
        if status == "created" and application is not None:
            return SkillObservation(status="succeeded", artifact_kind="action_result", summary="已查询到 Java 原提交结果，未重放业务写入。",
                reference=_reference("action", application.application_id), source_version="v1", factuality="verified",
                safe_facts={"submission_status": application.status})
        return SkillObservation(status="unavailable", artifact_kind="action_result", summary="原提交结果尚未核实；未重新提交，请稍后查询。",
            reference=_reference("reconcile", task_ref), source_version="v1", factuality="unavailable",
            safe_facts={"failure_code": "commit_result_unknown"})

    @staticmethod
    def invoke_tool(tool_call, context=None):
        from app.services import tool_registry as registry
        from app.services.tool_context import ToolExecutionContext
        from app.services.skill_catalog import assert_tool_allowed_for_skill, SkillPolicyError
        tool = registry.TOOLS.get(tool_call.name)
        if tool is None:
            raise registry.ToolNotFoundError(f"工具未注册：{tool_call.name}")
        effective = context or ToolExecutionContext()
        if effective.skill_id is not None:
            try:
                assert_tool_allowed_for_skill(effective.actor_role, effective.skill_id, tool_call.name)
            except SkillPolicyError as exc:
                raise registry.ToolAccessDeniedError("当前受控能力不允许调用该工具。") from exc
        registry._validate_tool_arguments(tool_call)
        return tool(tool_call.arguments, effective)
