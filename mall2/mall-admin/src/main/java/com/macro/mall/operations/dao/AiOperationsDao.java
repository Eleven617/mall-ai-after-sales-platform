package com.macro.mall.operations.dao;

import com.macro.mall.operations.domain.AiOperationsCaseView;
import com.macro.mall.operations.domain.OperationsHandoffCategoryCount;
import com.macro.mall.operations.domain.OperationsMetricCount;
import org.apache.ibatis.annotations.Param;

import java.util.Date;
import java.util.List;

/** Read-only, de-identified queries for the Build 19 operations role. */
public interface AiOperationsDao {
    List<AiOperationsCaseView> listRecentCases(@Param("limit") Integer limit);

    AiOperationsCaseView findCaseByCaseId(@Param("caseId") String caseId);

    List<OperationsMetricCount> countAfterSalesByStatus(@Param("fromTime") Date fromTime);

    List<OperationsMetricCount> countReasons(@Param("fromTime") Date fromTime);

    List<OperationsMetricCount> countOutboxByStatus(@Param("fromTime") Date fromTime);

    List<OperationsMetricCount> countDeliveryByStatus(@Param("fromTime") Date fromTime);

    Long countUniqueHandoffs(
            @Param("fromTime") Date fromTime,
            @Param("toTime") Date toTime
    );

    List<OperationsHandoffCategoryCount> countUniqueHandoffsByCategory(
            @Param("fromTime") Date fromTime,
            @Param("toTime") Date toTime
    );
}
