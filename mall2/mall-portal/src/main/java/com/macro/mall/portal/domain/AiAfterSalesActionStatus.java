package com.macro.mall.portal.domain;

/** Safe recovery projection for one confirmed cancel/modify action. */
public class AiAfterSalesActionStatus {
    private String status;
    private AiAfterSalesApplicationSummary application;

    public static AiAfterSalesActionStatus completed(AiAfterSalesApplicationSummary application) {
        AiAfterSalesActionStatus status = new AiAfterSalesActionStatus();
        status.setStatus("completed");
        status.setApplication(application);
        return status;
    }

    public static AiAfterSalesActionStatus notFound() {
        AiAfterSalesActionStatus status = new AiAfterSalesActionStatus();
        status.setStatus("not_found");
        return status;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public AiAfterSalesApplicationSummary getApplication() { return application; }
    public void setApplication(AiAfterSalesApplicationSummary application) { this.application = application; }
}
