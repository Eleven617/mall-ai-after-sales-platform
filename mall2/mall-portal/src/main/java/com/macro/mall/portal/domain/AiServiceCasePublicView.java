package com.macro.mall.portal.domain;

import java.util.Date;

/** Customer projection: no queue, assignee, internal note, member id or trace. */
public class AiServiceCasePublicView {
    private String caseId;
    private String category;
    private String state;
    private Integer stateVersion;
    private String publicStatus;
    private Boolean customerInformationRequired;
    private String requiredInformationType;
    private Boolean canCancel;
    private Boolean canReopen;
    private String lastPublicMessage;
    private Date updatedAt;

    public static AiServiceCasePublicView from(AiServiceCaseRecord record) {
        AiServiceCasePublicView view = new AiServiceCasePublicView();
        view.setCaseId(record.getCaseId());
        view.setCategory(record.getDiagnosisCategory());
        view.setState(record.getState());
        view.setStateVersion(record.getStateVersion());
        view.setPublicStatus(record.getPublicStatus());
        String state = record.getState();
        view.setCustomerInformationRequired("AWAITING_CUSTOMER_INFORMATION".equals(state));
        view.setRequiredInformationType(
                "AWAITING_CUSTOMER_INFORMATION".equals(state) ? record.getCustomerInformationType() : null
        );
        view.setCanCancel(
                "QUEUED".equals(state) || "CLAIMED".equals(state)
                        || "AWAITING_CUSTOMER_INFORMATION".equals(state) || "IN_REVIEW".equals(state)
        );
        view.setCanReopen(
                "RESOLVED".equals(state) && record.getUpdatedAt() != null
                        && System.currentTimeMillis() - record.getUpdatedAt().getTime() <= 7L * 24L * 60L * 60L * 1000L
        );
        view.setLastPublicMessage(record.getLastPublicMessage());
        view.setUpdatedAt(record.getUpdatedAt());
        return view;
    }

    public String getCaseId() { return caseId; }
    public void setCaseId(String caseId) { this.caseId = caseId; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public String getState() { return state; }
    public void setState(String state) { this.state = state; }
    public Integer getStateVersion() { return stateVersion; }
    public void setStateVersion(Integer stateVersion) { this.stateVersion = stateVersion; }
    public String getPublicStatus() { return publicStatus; }
    public void setPublicStatus(String publicStatus) { this.publicStatus = publicStatus; }
    public Boolean getCustomerInformationRequired() { return customerInformationRequired; }
    public void setCustomerInformationRequired(Boolean customerInformationRequired) { this.customerInformationRequired = customerInformationRequired; }
    public String getRequiredInformationType() { return requiredInformationType; }
    public void setRequiredInformationType(String requiredInformationType) { this.requiredInformationType = requiredInformationType; }
    public Boolean getCanCancel() { return canCancel; }
    public void setCanCancel(Boolean canCancel) { this.canCancel = canCancel; }
    public Boolean getCanReopen() { return canReopen; }
    public void setCanReopen(Boolean canReopen) { this.canReopen = canReopen; }
    public String getLastPublicMessage() { return lastPublicMessage; }
    public void setLastPublicMessage(String lastPublicMessage) { this.lastPublicMessage = lastPublicMessage; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
