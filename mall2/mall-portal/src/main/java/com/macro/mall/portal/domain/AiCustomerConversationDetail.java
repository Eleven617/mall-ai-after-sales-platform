package com.macro.mall.portal.domain;

import java.util.ArrayList;
import java.util.List;

/** A current member's complete customer-visible transcript. */
public class AiCustomerConversationDetail {
    private AiCustomerConversationSummary conversation;
    private List<AiCustomerConversationMessage> messages = new ArrayList<>();

    public AiCustomerConversationSummary getConversation() { return conversation; }
    public void setConversation(AiCustomerConversationSummary conversation) { this.conversation = conversation; }
    public List<AiCustomerConversationMessage> getMessages() { return messages; }
    public void setMessages(List<AiCustomerConversationMessage> messages) {
        this.messages = messages == null ? new ArrayList<>() : messages;
    }
}
