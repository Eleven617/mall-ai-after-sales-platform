package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCommand;
import com.macro.mall.portal.service.AiAfterSalesApplicationService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Explicitly opt-in local demonstration adapter.  It exists only to exercise
 * success/failure callbacks and is disabled in the default customer path.
 */
@Component
@ConditionalOnProperty(prefix = "after-sales.fulfillment.demo", name = "enabled", havingValue = "true")
public class DemoAiAfterSalesFulfillmentAdapter implements AiAfterSalesFulfillmentAdapter {
    private final AiAfterSalesApplicationService applicationService;

    @Value("${after-sales.fulfillment.demo.outcome:manual_required}")
    private String outcome;

    @Autowired
    public DemoAiAfterSalesFulfillmentAdapter(AiAfterSalesApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @Override
    public void dispatch(AiAfterSalesFulfillmentCommand command) {
        String normalized = "succeeded".equals(outcome) || "failed".equals(outcome)
                || "processing".equals(outcome) ? outcome : "manual_required";
        AiAfterSalesFulfillmentCallbackRequest callback = new AiAfterSalesFulfillmentCallbackRequest();
        callback.setApplicationId(command.getApplicationId());
        callback.setCallbackEventId("demo:" + command.getEventId());
        callback.setFulfillmentStatus(normalized);
        callback.setSource("demo_adapter");
        callback.setNote("演示适配器回执（仅测试/演示，不代表真实外部系统）。");
        applicationService.recordFulfillmentCallback(callback);
    }
}
