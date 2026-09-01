package com.macro.mall.serviceoperations.domain;

import java.util.Date;

/** Java-internal minimal row used to authorize deterministic human actions. */
public class AiServiceCaseProcessorRecord {
    private Long id;
    private String caseId;
    private Long memberId;
    private String queueRef;
    private String diagnosisCategory;
    private String priority;
    private String state;
    private Integer stateVersion;
    private String assigneeRef;
    private String publicStatus;
    private String customerInformationType;
    private String customerInformation;
    private String lastPublicMessage;
    private Date updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public Long getMemberId() { return memberId; }
    public void setMemberId(Long memberId) { this.memberId = memberId; }
    public String getQueueRef() { return queueRef; }
    public void setQueueRef(String queueRef) { this.queueRef = queueRef; }
    public String getDiagnosisCategory() { return diagnosisCategory; }
    public void setDiagnosisCategory(String diagnosisCategory) { this.diagnosisCategory = diagnosisCategory; }
    public String getPriority() { return priority; }
    public void setPriority(String priority) { this.priority = priority; }
    public String getState() { return state; }
    public void setState(String state) { this.state = state; }
    public Integer getStateVersion() { return stateVersion; }
    public void setStateVersion(Integer stateVersion) { this.stateVersion = stateVersion; }
    public String getAssigneeRef() { return assigneeRef; }
    public void setAssigneeRef(String assigneeRef) { this.assigneeRef = assigneeRef; }
    public String getPublicStatus() { return publicStatus; }
    public void setPublicStatus(String publicStatus) { this.publicStatus = publicStatus; }
    public String getCustomerInformationType() { return customerInformationType; }
    public void setCustomerInformationType(String customerInformationType) { this.customerInformationType = customerInformationType; }
    public String getCustomerInformation() { return customerInformation; }
    public void setCustomerInformation(String customerInformation) { this.customerInformation = customerInformation; }
    public String getLastPublicMessage() { return lastPublicMessage; }
    public void setLastPublicMessage(String lastPublicMessage) { this.lastPublicMessage = lastPublicMessage; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
