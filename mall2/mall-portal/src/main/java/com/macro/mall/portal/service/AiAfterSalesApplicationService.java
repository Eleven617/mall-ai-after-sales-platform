package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.AiAfterSalesApplicationSummary;
import com.macro.mall.portal.domain.AiAfterSalesActionRequest;
import com.macro.mall.portal.domain.AiAfterSalesActionStatus;
import com.macro.mall.portal.domain.AiAfterSalesApplyRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilityRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilitySummary;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesSubmissionStatus;

import java.util.List;

/**
 * One business boundary for all new after-sales application kinds. It owns
 * authorization, factual eligibility, idempotent writes, and customer-safe
 * status projections; FastAPI never accesses the order database directly.
 */
public interface AiAfterSalesApplicationService {
    AiAfterSalesEligibilitySummary checkEligibility(AiAfterSalesEligibilityRequest request);

    AiAfterSalesApplicationSummary createForAi(AiAfterSalesApplyRequest request);

    AiAfterSalesSubmissionStatus getSubmissionStatus(String idempotencyKey);

    List<AiAfterSalesApplicationSummary> listForAiCurrentMember();

    AiAfterSalesApplicationSummary cancelForAiCurrentMember(
            Long applicationId,
            AiAfterSalesActionRequest request
    );

    AiAfterSalesApplicationSummary modifyForAiCurrentMember(
            Long applicationId,
            AiAfterSalesActionRequest request
    );

    AiAfterSalesActionStatus getActionStatus(String actionId);

    AiAfterSalesApplicationSummary recordFulfillmentCallback(
            AiAfterSalesFulfillmentCallbackRequest request
    );
}
