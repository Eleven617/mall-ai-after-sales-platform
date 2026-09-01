package com.macro.mall.portal.domain;

/**
 * Customer-safe factual result. It says whether the business system permits
 * creating a request, not whether a human reviewer has finally approved it.
 */
public class AiAfterSalesEligibilitySummary {
    private String orderSn;
    private String applicationType;
    private String applicationTypeLabel;
    private String orderStatus;
    private boolean eligible;
    private boolean requiresProductSelection;
    private String decision;
    private String message;
    private String productName;
    private String productAttr;

    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getApplicationType() { return applicationType; }
    public void setApplicationType(String applicationType) { this.applicationType = applicationType; }
    public String getApplicationTypeLabel() { return applicationTypeLabel; }
    public void setApplicationTypeLabel(String applicationTypeLabel) { this.applicationTypeLabel = applicationTypeLabel; }
    public String getOrderStatus() { return orderStatus; }
    public void setOrderStatus(String orderStatus) { this.orderStatus = orderStatus; }
    public boolean isEligible() { return eligible; }
    public void setEligible(boolean eligible) { this.eligible = eligible; }
    public boolean isRequiresProductSelection() { return requiresProductSelection; }
    public void setRequiresProductSelection(boolean requiresProductSelection) { this.requiresProductSelection = requiresProductSelection; }
    public String getDecision() { return decision; }
    public void setDecision(String decision) { this.decision = decision; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getProductAttr() { return productAttr; }
    public void setProductAttr(String productAttr) { this.productAttr = productAttr; }
}
