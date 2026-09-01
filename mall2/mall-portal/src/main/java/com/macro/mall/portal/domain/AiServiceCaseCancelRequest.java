package com.macro.mall.portal.domain;

/** Explicit idempotent customer cancellation for still-pending service cases. */
public class AiServiceCaseCancelRequest {
    private Integer expectedVersion;
    private String idempotencyKey;

    public Integer getExpectedVersion() { return expectedVersion; }
    public void setExpectedVersion(Integer expectedVersion) { this.expectedVersion = expectedVersion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
}
