package com.macro.mall.portal.domain;

import java.util.Date;

/** Browser-safe conversation-list item. Its title never contains raw customer input. */
public class AiCustomerConversationSummary {
    private String conversationId;
    private String title;
    private Integer messageCount;
    private Date createdAt;
    private Date updatedAt;

    public static AiCustomerConversationSummary from(AiCustomerConversationRecord record) {
        AiCustomerConversationSummary summary = new AiCustomerConversationSummary();
        summary.setConversationId(record.getConversationId());
        summary.setTitle(record.getTitle());
        summary.setMessageCount(record.getMessageCount() == null ? 0 : record.getMessageCount());
        summary.setCreatedAt(record.getCreateTime());
        summary.setUpdatedAt(record.getUpdateTime());
        return summary;
    }

    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public Integer getMessageCount() { return messageCount; }
    public void setMessageCount(Integer messageCount) { this.messageCount = messageCount; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
