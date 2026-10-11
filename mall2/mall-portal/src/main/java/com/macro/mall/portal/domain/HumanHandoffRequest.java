package com.macro.mall.portal.domain;

/** Closed, structured projection: deliberately accepts no free customer text. */
public class HumanHandoffRequest {
    public String requestRef;
    public String scopeKey;
    public String contentHash;
    public String triggerSource;
    public String entryChannel;
    public String businessTopic;
    public String customerReason;
    public String taskRef;
    public String stage;
    public int planVersion;
    public int completedSteps;
    public int verifiedEvidenceCount;
}
