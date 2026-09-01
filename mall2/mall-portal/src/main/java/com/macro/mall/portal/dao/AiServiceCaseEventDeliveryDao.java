package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiServiceCaseEventDelivery;

/** Duplicate-safe consumer receipt boundary for human-collaboration events. */
public interface AiServiceCaseEventDeliveryDao {
    int insertIgnore(AiServiceCaseEventDelivery delivery);
}
