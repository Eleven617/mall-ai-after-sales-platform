package com.macro.mall.portal.domain;

/**
 * Internal authenticated adapter callback.  A unique callbackEventId makes
 * RabbitMQ or network redelivery idempotent before a lifecycle is changed.
 */
public class AiAfterSalesFulfillmentCallbackRequest {
    private Long applicationId;
    private String callbackEventId;
    private String fulfillmentStatus;
    private String note;
    private String source;

    public Long getApplicationId() { return applicationId; }
    public void setApplicationId(Long applicationId) { this.applicationId = applicationId; }
    public String getCallbackEventId() { return callbackEventId; }
    public void setCallbackEventId(String callbackEventId) { this.callbackEventId = callbackEventId; }
    public String getFulfillmentStatus() { return fulfillmentStatus; }
    public void setFulfillmentStatus(String fulfillmentStatus) { this.fulfillmentStatus = fulfillmentStatus; }
    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
}
