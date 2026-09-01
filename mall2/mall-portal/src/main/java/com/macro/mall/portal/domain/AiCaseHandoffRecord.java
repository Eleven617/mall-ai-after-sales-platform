package com.macro.mall.portal.domain;

import java.util.Date;

/** Java-internal persistence shape for Build 19 case handoffs. */
public class AiCaseHandoffRecord {
    private Long id;
    private String caseId;
    private Long memberId;
    private String caseKey;
    private String sourceFlow;
    private String diagnosisCategory;
    private String evidenceStatus;
    private String handoffReason;
    private Boolean requiresHumanReview;
    private String caseStatus;
    private String schemaVersion;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public Long getMemberId() { return memberId; }
    public void setMemberId(Long memberId) { this.memberId = memberId; }
    public String getCaseKey() { return caseKey; }
    public void setCaseKey(String caseKey) { this.caseKey = caseKey; }
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
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
