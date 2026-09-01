package com.macro.mall.portal.domain;

/** Customer may only submit a bounded, explicitly requested information field. */
public class AiServiceCaseCustomerInformationRequest {
    private Integer expectedVersion;
    private String idempotencyKey;
    private String informationType;
    private String information;

    public Integer getExpectedVersion() { return expectedVersion; }
    public void setExpectedVersion(Integer expectedVersion) { this.expectedVersion = expectedVersion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
    public String getInformationType() { return informationType; }
    public void setInformationType(String informationType) { this.informationType = informationType; }
    public String getInformation() { return information; }
    public void setInformation(String information) { this.information = information; }
}
