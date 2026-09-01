package com.macro.mall.operations.service;

import com.macro.mall.operations.domain.AiOperationsCaseView;
import com.macro.mall.operations.domain.AiOperationsMetrics;

import java.util.List;

/** Read-only operations data contract; it contains no business mutation API. */
public interface AiOperationsService {
    List<AiOperationsCaseView> listRecentCases(Integer limit);

    AiOperationsCaseView getCase(String caseId);

    AiOperationsMetrics getMetrics(Integer windowDays);
}
