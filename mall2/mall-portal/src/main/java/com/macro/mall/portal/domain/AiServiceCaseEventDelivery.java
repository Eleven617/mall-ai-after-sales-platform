package com.macro.mall.portal.domain;

import java.util.Date;

/** Idempotent receipt record for an asynchronous service-case status event. */
public class AiServiceCaseEventDelivery {
    private String eventId;
    private String caseId;
    private String deliveryStatus;
    private Date receivedAt;

    public String getEventId() { return eventId; }
    public void setEventId(String eventId) { this.eventId = eventId; }
    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public String getDeliveryStatus() { return deliveryStatus; }
    public void setDeliveryStatus(String deliveryStatus) { this.deliveryStatus = deliveryStatus; }
    public Date getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Date receivedAt) { this.receivedAt = receivedAt; }
}
