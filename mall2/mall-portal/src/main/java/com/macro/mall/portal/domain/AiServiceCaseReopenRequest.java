package com.macro.mall.portal.domain;

/** A bounded customer request to reopen a recently resolved service case. */
public class AiServiceCaseReopenRequest {
    private Integer expectedVersion;
    private String idempotencyKey;
    private String reason;

    public Integer getExpectedVersion() { return expectedVersion; }
    public void setExpectedVersion(Integer expectedVersion) { this.expectedVersion = expectedVersion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
}
