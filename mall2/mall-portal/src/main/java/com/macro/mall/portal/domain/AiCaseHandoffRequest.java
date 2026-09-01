package com.macro.mall.portal.domain;

/**
 * Narrow request accepted only from the AI service on behalf of the current
 * member. It deliberately contains no user-provided free text or identifiers.
 */
public class AiCaseHandoffRequest {
    private String caseKey;
    private String sourceFlow;
    private String diagnosisCategory;
    private String evidenceStatus;
    private String handoffReason;
    private Boolean requiresHumanReview;
    private String schemaVersion;
    private String correlationRef;

    public String getCaseKey() {
        return caseKey;
    }

    public void setCaseKey(String caseKey) {
        this.caseKey = caseKey;
    }

    public String getSourceFlow() {
        return sourceFlow;
    }

    public void setSourceFlow(String sourceFlow) {
        this.sourceFlow = sourceFlow;
    }

    public String getDiagnosisCategory() {
        return diagnosisCategory;
    }

    public void setDiagnosisCategory(String diagnosisCategory) {
        this.diagnosisCategory = diagnosisCategory;
    }

    public String getEvidenceStatus() {
        return evidenceStatus;
    }

    public void setEvidenceStatus(String evidenceStatus) {
        this.evidenceStatus = evidenceStatus;
    }

    public String getHandoffReason() {
        return handoffReason;
    }

    public void setHandoffReason(String handoffReason) {
        this.handoffReason = handoffReason;
    }

    public Boolean getRequiresHumanReview() {
        return requiresHumanReview;
    }

    public void setRequiresHumanReview(Boolean requiresHumanReview) {
        this.requiresHumanReview = requiresHumanReview;
    }

    public String getSchemaVersion() {
        return schemaVersion;
    }

    public void setSchemaVersion(String schemaVersion) {
        this.schemaVersion = schemaVersion;
    }

    public String getCorrelationRef() { return correlationRef; }
    public void setCorrelationRef(String correlationRef) { this.correlationRef = correlationRef; }
}
