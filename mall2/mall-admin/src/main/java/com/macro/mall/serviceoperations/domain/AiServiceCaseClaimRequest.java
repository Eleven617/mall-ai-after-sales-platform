package com.macro.mall.serviceoperations.domain;

/** Explicit, versioned claim of one queued minimal service case. */
public class AiServiceCaseClaimRequest {
    private Integer expectedVersion;
    private String idempotencyKey;

    public Integer getExpectedVersion() { return expectedVersion; }
    public void setExpectedVersion(Integer expectedVersion) { this.expectedVersion = expectedVersion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
}
