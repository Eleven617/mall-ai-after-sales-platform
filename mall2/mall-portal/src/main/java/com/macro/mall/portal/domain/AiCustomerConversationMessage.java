package com.macro.mall.portal.domain;

import java.util.Date;

/** Owner-visible message; the optional payload is already the public DTO. */
public class AiCustomerConversationMessage {
    private Long id;
    private String messageId;
    private String conversationId;
    private Integer sequenceNo;
    private String role;
    private String content;
    private String publicResponseJson;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getMessageId() { return messageId; }
    public void setMessageId(String messageId) { this.messageId = messageId; }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }
    public Integer getSequenceNo() { return sequenceNo; }
    public void setSequenceNo(Integer sequenceNo) { this.sequenceNo = sequenceNo; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getPublicResponseJson() { return publicResponseJson; }
    public void setPublicResponseJson(String publicResponseJson) { this.publicResponseJson = publicResponseJson; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
