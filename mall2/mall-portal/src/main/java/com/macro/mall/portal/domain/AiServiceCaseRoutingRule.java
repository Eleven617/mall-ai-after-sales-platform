package com.macro.mall.portal.domain;

/** Deterministic, database-backed routing allow-list; models never choose an assignee. */
public class AiServiceCaseRoutingRule {
    private String diagnosisCategory;
    private String priority;
    private String eligibleQueueRef;
    private String requiredFacts;
    private String policyVersion;
    private Boolean active;

    public String getDiagnosisCategory() { return diagnosisCategory; }
    public void setDiagnosisCategory(String diagnosisCategory) { this.diagnosisCategory = diagnosisCategory; }
    public String getPriority() { return priority; }
    public void setPriority(String priority) { this.priority = priority; }
    public String getEligibleQueueRef() { return eligibleQueueRef; }
    public void setEligibleQueueRef(String eligibleQueueRef) { this.eligibleQueueRef = eligibleQueueRef; }
    public String getRequiredFacts() { return requiredFacts; }
    public void setRequiredFacts(String requiredFacts) { this.requiredFacts = requiredFacts; }
    public String getPolicyVersion() { return policyVersion; }
    public void setPolicyVersion(String policyVersion) { this.policyVersion = policyVersion; }
    public Boolean getActive() { return active; }
    public void setActive(Boolean active) { this.active = active; }
}
