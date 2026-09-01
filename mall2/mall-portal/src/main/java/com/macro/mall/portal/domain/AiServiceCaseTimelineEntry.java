package com.macro.mall.portal.domain;

import java.util.Date;

/** Customer-safe action timeline projection. */
public class AiServiceCaseTimelineEntry {
    private String actionType;
    private String resultCode;
    private String publicMessage;
    private Date createdAt;

    public String getActionType() { return actionType; }
    public void setActionType(String actionType) { this.actionType = actionType; }
    public String getResultCode() { return resultCode; }
    public void setResultCode(String resultCode) { this.resultCode = resultCode; }
    public String getPublicMessage() { return publicMessage; }
    public void setPublicMessage(String publicMessage) { this.publicMessage = publicMessage; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
}
