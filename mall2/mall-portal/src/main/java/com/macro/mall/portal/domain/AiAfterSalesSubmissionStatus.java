package com.macro.mall.portal.domain;

/** Result of resolving a confirmed generic after-sales submission. */
public class AiAfterSalesSubmissionStatus {
    private String status;
    private AiAfterSalesApplicationSummary application;

    public static AiAfterSalesSubmissionStatus created(AiAfterSalesApplicationSummary application) {
        AiAfterSalesSubmissionStatus result = new AiAfterSalesSubmissionStatus();
        result.setStatus("created");
        result.setApplication(application);
        return result;
    }

    public static AiAfterSalesSubmissionStatus notFound() {
        AiAfterSalesSubmissionStatus result = new AiAfterSalesSubmissionStatus();
        result.setStatus("not_found");
        return result;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public AiAfterSalesApplicationSummary getApplication() { return application; }
    public void setApplication(AiAfterSalesApplicationSummary application) { this.application = application; }
}
