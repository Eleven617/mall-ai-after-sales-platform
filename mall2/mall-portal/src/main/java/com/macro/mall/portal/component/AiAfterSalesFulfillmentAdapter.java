package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCommand;

/**
 * Contract boundary for payment, warehouse, shipment or repair integrations.
 * An implementation must report a trusted callback; it cannot mark the
 * customer-facing application successful merely by receiving a queue message.
 */
public interface AiAfterSalesFulfillmentAdapter {
    void dispatch(AiAfterSalesFulfillmentCommand command);
}
