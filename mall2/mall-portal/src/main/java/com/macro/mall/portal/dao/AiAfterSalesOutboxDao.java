package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiAfterSalesOutboxEvent;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** Persistence boundary for the Build 18 transactional outbox. */
public interface AiAfterSalesOutboxDao {
    int insert(AiAfterSalesOutboxEvent event);

    List<AiAfterSalesOutboxEvent> findReadyForPublishing(@Param("limit") int limit);

    int claimForPublishing(
            @Param("id") Long id,
            @Param("leaseSeconds") long leaseSeconds
    );

    int markPublished(@Param("id") Long id);

    int markPublishFailure(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("retryDelaySeconds") Integer retryDelaySeconds,
            @Param("lastError") String lastError
    );
}
