package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiAfterSalesActionRecord;
import org.apache.ibatis.annotations.Param;

/** Durable idempotency boundary for confirmed customer cancel/modify actions. */
public interface AiAfterSalesActionDao {
    AiAfterSalesActionRecord findByMemberIdAndActionId(
            @Param("memberId") Long memberId,
            @Param("actionId") String actionId
    );

    int insertIgnore(AiAfterSalesActionRecord record);
}
