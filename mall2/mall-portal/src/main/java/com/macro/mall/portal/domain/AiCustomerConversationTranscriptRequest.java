package com.macro.mall.portal.domain;

import java.util.ArrayList;
import java.util.List;

/** A two-message customer/assistant exchange written atomically by the AI service. */
public class AiCustomerConversationTranscriptRequest {
    private String title;
    private List<AiCustomerConversationTranscriptMessage> messages = new ArrayList<>();

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public List<AiCustomerConversationTranscriptMessage> getMessages() { return messages; }
    public void setMessages(List<AiCustomerConversationTranscriptMessage> messages) {
        this.messages = messages == null ? new ArrayList<>() : messages;
    }
}
