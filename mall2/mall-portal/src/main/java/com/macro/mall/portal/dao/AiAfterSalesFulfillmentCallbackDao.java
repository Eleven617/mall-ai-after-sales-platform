package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRecord;
import org.apache.ibatis.annotations.Param;

/** Idempotent audit gate for an authenticated fulfillment callback. */
public interface AiAfterSalesFulfillmentCallbackDao {
    AiAfterSalesFulfillmentCallbackRecord findByCallbackEventId(
            @Param("callbackEventId") String callbackEventId
    );

    int insertIgnore(AiAfterSalesFulfillmentCallbackRecord record);
}
