package com.macro.mall.serviceoperations.service;

import com.macro.mall.serviceoperations.domain.AiServiceCaseActionRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseClaimRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorView;

import java.util.List;

/** Authorized human handling of minimal AI service cases, never order writes. */
public interface AiServiceOperationsService {
    List<AiServiceCaseProcessorView> listVisible(String username, Integer limit);
    AiServiceCaseProcessorView claim(
            String caseId, AiServiceCaseClaimRequest request, String username, String correlationRef
    );
    AiServiceCaseProcessorView act(
            String caseId, AiServiceCaseActionRequest request, String username, String correlationRef
    );
}
