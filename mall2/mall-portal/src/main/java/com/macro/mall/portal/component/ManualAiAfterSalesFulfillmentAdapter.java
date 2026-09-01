package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCommand;
import com.macro.mall.portal.service.AiAfterSalesApplicationService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Default adapter for local deployments without a configured external system.
 * It truthfully changes the fulfillment state to manual-required; it never
 * manufactures a payment, warehouse or shipping success.
 */
@Component
@ConditionalOnProperty(
        prefix = "after-sales.fulfillment.demo",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true
)
public class ManualAiAfterSalesFulfillmentAdapter implements AiAfterSalesFulfillmentAdapter {
    private final AiAfterSalesApplicationService applicationService;

    @Autowired
    public ManualAiAfterSalesFulfillmentAdapter(AiAfterSalesApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @Override
    public void dispatch(AiAfterSalesFulfillmentCommand command) {
        AiAfterSalesFulfillmentCallbackRequest callback = new AiAfterSalesFulfillmentCallbackRequest();
        callback.setApplicationId(command.getApplicationId());
        callback.setCallbackEventId("manual:" + command.getEventId());
        callback.setFulfillmentStatus("manual_required");
        callback.setSource("manual_adapter");
        callback.setNote("当前环境未配置支付、仓储、物流或维修适配器，已转人工履约。");
        applicationService.recordFulfillmentCallback(callback);
    }
}
