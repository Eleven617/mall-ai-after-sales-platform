package com.macro.mall.portal.domain;

import java.util.Date;

/** Internal audit row for an idempotent fulfillment callback. */
public class AiAfterSalesFulfillmentCallbackRecord {
    private Long id;
    private String callbackEventId;
    private Long applicationId;
    private String fulfillmentStatus;
    private String source;
    private String note;
    private Date callbackTime;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getCallbackEventId() { return callbackEventId; }
    public void setCallbackEventId(String callbackEventId) { this.callbackEventId = callbackEventId; }
    public Long getApplicationId() { return applicationId; }
    public void setApplicationId(Long applicationId) { this.applicationId = applicationId; }
    public String getFulfillmentStatus() { return fulfillmentStatus; }
    public void setFulfillmentStatus(String fulfillmentStatus) { this.fulfillmentStatus = fulfillmentStatus; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
    public Date getCallbackTime() { return callbackTime; }
    public void setCallbackTime(Date callbackTime) { this.callbackTime = callbackTime; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
