"""Strict public and processor contracts for Java-owned human service cases."""

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class StrictServiceCaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ServiceCaseCategory = Literal[
    "delivery_in_transit",
    "delivery_exception",
    "order_state_review",
    "facts_incomplete",
    "policy_consultation",
    "policy_insufficient",
    "tool_failure",
    "needs_order_identifier",
]
ServiceCaseState = Literal[
    "QUEUED",
    "CLAIMED",
    "AWAITING_CUSTOMER_INFORMATION",
    "IN_REVIEW",
    "RESOLVED",
    "REOPENED",
    "CLOSED",
    "CANCELLED",
]
ServiceCaseInformationType = Literal["problem_description", "purchase_context"]
ProcessorAction = Literal["request_information", "start_review", "resolve", "close"]


class CustomerServiceCaseView(StrictServiceCaseModel):
    """Customer projection: never queue, assignee, note, trace or owner id."""

    case_id: str = Field(
        validation_alias=AliasChoices("case_id", "caseId"),
        pattern=r"^[a-f0-9-]{36}$",
    )
    category: ServiceCaseCategory
    state: ServiceCaseState
    state_version: int = Field(
        validation_alias=AliasChoices("state_version", "stateVersion"), ge=1
    )
    public_status: str = Field(
        validation_alias=AliasChoices("public_status", "publicStatus"), min_length=1, max_length=160
    )
    customer_information_required: bool = Field(
        validation_alias=AliasChoices("customer_information_required", "customerInformationRequired")
    )
    required_information_type: ServiceCaseInformationType | None = Field(
        default=None,
        validation_alias=AliasChoices("required_information_type", "requiredInformationType"),
    )
    can_cancel: bool = Field(validation_alias=AliasChoices("can_cancel", "canCancel"))
    can_reopen: bool = Field(validation_alias=AliasChoices("can_reopen", "canReopen"))
    last_public_message: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_public_message", "lastPublicMessage"),
        max_length=500,
    )
    updated_at: datetime | None = Field(
        default=None, validation_alias=AliasChoices("updated_at", "updatedAt")
    )

    @model_validator(mode="after")
    def require_server_selected_information_type(self) -> "CustomerServiceCaseView":
        """Do not let a client invent a type when Java is awaiting a supplement."""

        if self.customer_information_required and self.required_information_type is None:
            raise ValueError("待补件案件缺少服务端指定的信息类型")
        if not self.customer_information_required and self.required_information_type is not None:
            raise ValueError("非待补件案件不应携带补件类型")
        return self


class CustomerServiceCaseTimelineEntry(StrictServiceCaseModel):
    action_type: str = Field(
        validation_alias=AliasChoices("action_type", "actionType"), min_length=1, max_length=48
    )
    result_code: str = Field(
        validation_alias=AliasChoices("result_code", "resultCode"), min_length=1, max_length=48
    )
    public_message: str = Field(
        validation_alias=AliasChoices("public_message", "publicMessage"), min_length=1, max_length=500
    )
    created_at: datetime | None = Field(
        default=None, validation_alias=AliasChoices("created_at", "createdAt")
    )


class CustomerServiceCaseInformationRequest(StrictServiceCaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")
    information_type: ServiceCaseInformationType
    information: str = Field(min_length=1, max_length=180)


class CustomerServiceCaseCancelRequest(StrictServiceCaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")


class CustomerServiceCaseReopenRequest(StrictServiceCaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")
    reason: str = Field(min_length=1, max_length=180)


class ServiceProcessorProfile(StrictServiceCaseModel):
    username: str = Field(min_length=1, max_length=64)
    capabilities: list[Literal["service_case_handling"]] = Field(default_factory=list, max_length=2)


class ServiceProcessorLoginRequest(StrictServiceCaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)


class ServiceProcessorLoginResponse(StrictServiceCaseModel):
    authorization: str = Field(min_length=8)
    processor: ServiceProcessorProfile


class ServiceProcessorCaseView(StrictServiceCaseModel):
    """Least-privileged processor projection; no member/order/raw chat/trace."""

    case_id: str = Field(
        validation_alias=AliasChoices("case_id", "caseId"), pattern=r"^[a-f0-9-]{36}$"
    )
    queue_ref: Literal["logistics_review", "policy_review", "general_after_sales"] = Field(
        validation_alias=AliasChoices("queue_ref", "queueRef")
    )
    diagnosis_category: ServiceCaseCategory = Field(
        validation_alias=AliasChoices("diagnosis_category", "diagnosisCategory")
    )
    priority: Literal["low", "normal", "high"]
    state: ServiceCaseState
    state_version: int = Field(
        validation_alias=AliasChoices("state_version", "stateVersion"), ge=1
    )
    assigned_to_me: bool = Field(
        validation_alias=AliasChoices("assigned_to_me", "assignedToMe")
    )
    public_status: str = Field(
        validation_alias=AliasChoices("public_status", "publicStatus"), min_length=1, max_length=160
    )
    customer_information_type: ServiceCaseInformationType | None = Field(
        default=None,
        validation_alias=AliasChoices("customer_information_type", "customerInformationType"),
    )
    customer_information: str | None = Field(
        default=None,
        validation_alias=AliasChoices("customer_information", "customerInformation"),
        max_length=240,
    )
    last_public_message: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_public_message", "lastPublicMessage"),
        max_length=500,
    )
    updated_at: datetime | None = Field(
        default=None, validation_alias=AliasChoices("updated_at", "updatedAt")
    )


class ServiceProcessorClaimRequest(StrictServiceCaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")


class ServiceProcessorActionRequest(StrictServiceCaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: ProcessorAction
    information_type: ServiceCaseInformationType | None = None
    public_message: str | None = Field(default=None, max_length=500)
    internal_note: str | None = Field(default=None, max_length=500)
