package com.macro.mall.serviceoperations.domain;

import java.util.Date;

/**
 * Human processor projection. It intentionally excludes member/order keys,
 * raw customer conversation, trace, case de-duplication key and all notes.
 */
public class AiServiceCaseProcessorView {
    private String caseId;
    private String queueRef;
    private String diagnosisCategory;
    private String priority;
    private String state;
    private Integer stateVersion;
    private Boolean assignedToMe;
    private String publicStatus;
    private String customerInformationType;
    private String customerInformation;
    private String lastPublicMessage;
    private Date updatedAt;

    public static AiServiceCaseProcessorView from(AiServiceCaseProcessorRecord record, String username) {
        AiServiceCaseProcessorView view = new AiServiceCaseProcessorView();
        view.setCaseId(record.getCaseId());
        view.setQueueRef(record.getQueueRef());
        view.setDiagnosisCategory(record.getDiagnosisCategory());
        view.setPriority(record.getPriority());
        view.setState(record.getState());
        view.setStateVersion(record.getStateVersion());
        boolean assigned = username != null && username.equals(record.getAssigneeRef());
        view.setAssignedToMe(assigned);
        view.setPublicStatus(record.getPublicStatus());
        // A queued item is deliberately preview-only. The bounded customer
        // supplement becomes visible only after a processor has claimed it.
        if (assigned) {
            view.setCustomerInformationType(record.getCustomerInformationType());
            view.setCustomerInformation(record.getCustomerInformation());
        }
        view.setLastPublicMessage(record.getLastPublicMessage());
        view.setUpdatedAt(record.getUpdatedAt());
        return view;
    }

    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
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
    public Boolean getAssignedToMe() { return assignedToMe; }
    public void setAssignedToMe(Boolean assignedToMe) { this.assignedToMe = assignedToMe; }
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
