package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.AiCustomerConversationDetail;
import com.macro.mall.portal.domain.AiCustomerConversationSummary;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptRequest;

import java.util.List;

/** Member-owned transcript history, separate from short-lived AI workflow state. */
public interface AiCustomerConversationService {
    AiCustomerConversationSummary createForCurrentMember(String conversationId);

    List<AiCustomerConversationSummary> listForCurrentMember();

    AiCustomerConversationDetail getForCurrentMember(String conversationId);

    void appendTranscriptForCurrentMember(
            String conversationId,
            AiCustomerConversationTranscriptRequest request
    );

    void deleteForCurrentMember(String conversationId);
}
