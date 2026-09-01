package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiServiceCaseOutboxEvent;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** Persistence contract for service-case transactional outbox delivery. */
public interface AiServiceCaseOutboxDao {
    List<AiServiceCaseOutboxEvent> findReadyForPublishing(@Param("limit") int limit);

    int claimForPublishing(@Param("id") Long id, @Param("leaseSeconds") long leaseSeconds);

    int markPublished(@Param("id") Long id);

    int markPublishFailure(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("retryDelaySeconds") Integer retryDelaySeconds,
            @Param("lastError") String lastError
    );
}
