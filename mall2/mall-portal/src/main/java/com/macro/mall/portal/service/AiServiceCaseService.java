package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.AiServiceCaseCancelRequest;
import com.macro.mall.portal.domain.AiServiceCaseCustomerInformationRequest;
import com.macro.mall.portal.domain.AiServiceCasePublicView;
import com.macro.mall.portal.domain.AiServiceCaseReopenRequest;
import com.macro.mall.portal.domain.AiServiceCaseTimelineEntry;

import java.util.List;

/** Member-scoped public handling surface for an already-created minimal case. */
public interface AiServiceCaseService {
    List<AiServiceCasePublicView> listMine();
    List<AiServiceCaseTimelineEntry> timelineMine(String caseId);
    AiServiceCasePublicView submitCustomerInformation(
            String caseId, AiServiceCaseCustomerInformationRequest request, String correlationRef
    );
    AiServiceCasePublicView cancelMine(String caseId, AiServiceCaseCancelRequest request, String correlationRef);
    AiServiceCasePublicView reopenMine(String caseId, AiServiceCaseReopenRequest request, String correlationRef);
}
