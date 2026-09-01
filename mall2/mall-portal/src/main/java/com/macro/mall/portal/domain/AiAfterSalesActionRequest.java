package com.macro.mall.portal.domain;

/**
 * Internal FastAPI-to-Java request sent only after a Redis-held confirmation.
 * The browser never receives or supplies actionId/contentHash.
 */
public class AiAfterSalesActionRequest {
    private String actionId;
    private String contentHash;
    private String reason;
    private String description;

    public String getActionId() { return actionId; }
    public void setActionId(String actionId) { this.actionId = actionId; }
    public String getContentHash() { return contentHash; }
    public void setContentHash(String contentHash) { this.contentHash = contentHash; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
}
