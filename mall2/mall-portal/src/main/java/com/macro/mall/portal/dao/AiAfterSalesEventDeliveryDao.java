package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiAfterSalesEventDelivery;

/**
 * `insert ignore` makes an at-least-once broker redelivery safe for the
 * consumer. It is intentionally separate from return-submission idempotency.
 */
public interface AiAfterSalesEventDeliveryDao {
    int insertIgnore(AiAfterSalesEventDelivery delivery);
}
