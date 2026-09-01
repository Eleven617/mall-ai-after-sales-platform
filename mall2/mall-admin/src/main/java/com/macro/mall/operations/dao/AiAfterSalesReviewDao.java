package com.macro.mall.operations.dao;

import com.macro.mall.operations.domain.AiAfterSalesReviewRecord;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** MyBatis boundary for the generic after-sales review lifecycle. */
public interface AiAfterSalesReviewDao {
    List<AiAfterSalesReviewRecord> listForReview(
            @Param("status") String status,
            @Param("limit") Integer limit
    );

    AiAfterSalesReviewRecord findById(@Param("id") Long id);

    int reviewPending(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("statusNote") String statusNote,
            @Param("reviewedBy") String reviewedBy,
            @Param("fulfillmentStatus") String fulfillmentStatus,
            @Param("fulfillmentNote") String fulfillmentNote
    );

    int insertReviewEvent(
            @Param("eventId") String eventId,
            @Param("applicationId") Long applicationId,
            @Param("memberId") Long memberId,
            @Param("applicationSource") String applicationSource,
            @Param("eventType") String eventType
    );
}
