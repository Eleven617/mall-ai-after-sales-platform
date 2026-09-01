package com.macro.mall.portal.domain;

import java.util.Date;

/**
 * A committed service-case transition waiting for broker publication.  It
 * deliberately contains opaque identifiers only, never customer text or an
 * internal processor note.
 */
public class AiServiceCaseOutboxEvent {
    private Long id;
    private String eventId;
    private String caseId;
    private Long memberId;
    private String eventType;
    private Integer stateVersion;
    private String correlationRef;
    private String status;
    private Integer attemptCount;
    private Date availableAt;
    private Date leaseUntil;
    private Date publishedAt;
    private String lastError;
    private Date createdAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getEventId() { return eventId; }
    public void setEventId(String eventId) { this.eventId = eventId; }
    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public Long getMemberId() { return memberId; }
    public void setMemberId(Long memberId) { this.memberId = memberId; }
    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }
    public Integer getStateVersion() { return stateVersion; }
    public void setStateVersion(Integer stateVersion) { this.stateVersion = stateVersion; }
    public String getCorrelationRef() { return correlationRef; }
    public void setCorrelationRef(String correlationRef) { this.correlationRef = correlationRef; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getAttemptCount() { return attemptCount; }
    public void setAttemptCount(Integer attemptCount) { this.attemptCount = attemptCount; }
    public Date getAvailableAt() { return availableAt; }
    public void setAvailableAt(Date availableAt) { this.availableAt = availableAt; }
    public Date getLeaseUntil() { return leaseUntil; }
    public void setLeaseUntil(Date leaseUntil) { this.leaseUntil = leaseUntil; }
    public Date getPublishedAt() { return publishedAt; }
    public void setPublishedAt(Date publishedAt) { this.publishedAt = publishedAt; }
    public String getLastError() { return lastError; }
    public void setLastError(String lastError) { this.lastError = lastError; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
}
