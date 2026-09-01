package com.macro.mall.serviceoperations.domain;

/**
 * The processor can only choose a deterministic state-machine action.  Public
 * wording and internal notes are intentionally separate fields.
 */
public class AiServiceCaseActionRequest {
    private Integer expectedVersion;
    private String idempotencyKey;
    private String action;
    private String informationType;
    private String publicMessage;
    private String internalNote;

    public Integer getExpectedVersion() { return expectedVersion; }
    public void setExpectedVersion(Integer expectedVersion) { this.expectedVersion = expectedVersion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
    public String getAction() { return action; }
    public void setAction(String action) { this.action = action; }
    public String getInformationType() { return informationType; }
    public void setInformationType(String informationType) { this.informationType = informationType; }
    public String getPublicMessage() { return publicMessage; }
    public void setPublicMessage(String publicMessage) { this.publicMessage = publicMessage; }
    public String getInternalNote() { return internalNote; }
    public void setInternalNote(String internalNote) { this.internalNote = internalNote; }
}
