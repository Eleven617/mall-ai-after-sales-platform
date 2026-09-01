package com.macro.mall.operations.domain;

import java.util.Date;

/**
 * The only per-case projection available to an authorized operations role.
 * It intentionally excludes member identity, raw text, order data and tool
 * payloads.
 */
public class AiOperationsCaseView {
    private String caseId;
    private String sourceFlow;
    private String diagnosisCategory;
    private String evidenceStatus;
    private String handoffReason;
    private Boolean requiresHumanReview;
    private String caseStatus;
    private String schemaVersion;
    private Date createdAt;
    private Date updatedAt;

    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public String getSourceFlow() { return sourceFlow; }
    public void setSourceFlow(String sourceFlow) { this.sourceFlow = sourceFlow; }
    public String getDiagnosisCategory() { return diagnosisCategory; }
    public void setDiagnosisCategory(String diagnosisCategory) { this.diagnosisCategory = diagnosisCategory; }
    public String getEvidenceStatus() { return evidenceStatus; }
    public void setEvidenceStatus(String evidenceStatus) { this.evidenceStatus = evidenceStatus; }
    public String getHandoffReason() { return handoffReason; }
    public void setHandoffReason(String handoffReason) { this.handoffReason = handoffReason; }
    public Boolean getRequiresHumanReview() { return requiresHumanReview; }
    public void setRequiresHumanReview(Boolean requiresHumanReview) { this.requiresHumanReview = requiresHumanReview; }
    public String getCaseStatus() { return caseStatus; }
    public void setCaseStatus(String caseStatus) { this.caseStatus = caseStatus; }
    public String getSchemaVersion() { return schemaVersion; }
    public void setSchemaVersion(String schemaVersion) { this.schemaVersion = schemaVersion; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
