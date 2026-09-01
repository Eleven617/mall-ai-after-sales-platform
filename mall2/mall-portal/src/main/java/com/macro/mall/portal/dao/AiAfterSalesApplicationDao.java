package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiAfterSalesApplicationRecord;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** MyBatis boundary for the unified, customer-scoped after-sales core. */
public interface AiAfterSalesApplicationDao {
    int insertIgnore(AiAfterSalesApplicationRecord record);

    AiAfterSalesApplicationRecord findByMemberIdAndIdempotencyKey(
            @Param("memberId") Long memberId,
            @Param("idempotencyKey") String idempotencyKey
    );

    AiAfterSalesApplicationRecord findByApplicationKey(@Param("applicationKey") String applicationKey);

    AiAfterSalesApplicationRecord findByOpenScopeKey(@Param("openScopeKey") String openScopeKey);

    AiAfterSalesApplicationRecord findByIdAndMemberId(
            @Param("id") Long id,
            @Param("memberId") Long memberId
    );

    AiAfterSalesApplicationRecord findById(@Param("id") Long id);

    List<AiAfterSalesApplicationRecord> listByMemberId(@Param("memberId") Long memberId);

    int cancelPending(@Param("id") Long id, @Param("memberId") Long memberId);

    int modifyPending(
            @Param("id") Long id,
            @Param("memberId") Long memberId,
            @Param("reason") String reason,
            @Param("description") String description
    );

    int supplementAccepted(
            @Param("id") Long id,
            @Param("memberId") Long memberId,
            @Param("supplement") String supplement
    );

    int updateFulfillmentFromCallback(
            @Param("id") Long id,
            @Param("applicationStatus") String applicationStatus,
            @Param("fulfillmentStatus") String fulfillmentStatus,
            @Param("fulfillmentNote") String fulfillmentNote
    );
}
