package com.macro.mall.portal.domain;

import java.util.Date;

/**
 * Persistence model for a new unified application. It remains internal to
 * Java; public responses use {@link AiAfterSalesApplicationSummary} instead.
 */
public class AiAfterSalesApplicationRecord {
    private Long id;
    private Long memberId;
    private Long orderId;
    private Long orderItemId;
    private String orderSn;
    private String applicationType;
    private String productName;
    private String productAttr;
    private String reason;
    private String description;
    private String customerSupplement;
    private String status;
    private String statusNote;
    private String fulfillmentStatus;
    private String fulfillmentNote;
    private Date fulfillmentUpdatedAt;
    private String applicationKey;
    private String openScopeKey;
    private String idempotencyKey;
    private String requestFingerprint;
    private Date createTime;
    private Date updateTime;
    private Date cancelledAt;
    private String reviewedBy;
    private Date reviewedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getMemberId() { return memberId; }
    public void setMemberId(Long memberId) { this.memberId = memberId; }
    public Long getOrderId() { return orderId; }
    public void setOrderId(Long orderId) { this.orderId = orderId; }
    public Long getOrderItemId() { return orderItemId; }
    public void setOrderItemId(Long orderItemId) { this.orderItemId = orderItemId; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getApplicationType() { return applicationType; }
    public void setApplicationType(String applicationType) { this.applicationType = applicationType; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getProductAttr() { return productAttr; }
    public void setProductAttr(String productAttr) { this.productAttr = productAttr; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getCustomerSupplement() { return customerSupplement; }
    public void setCustomerSupplement(String customerSupplement) { this.customerSupplement = customerSupplement; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getStatusNote() { return statusNote; }
    public void setStatusNote(String statusNote) { this.statusNote = statusNote; }
    public String getFulfillmentStatus() { return fulfillmentStatus; }
    public void setFulfillmentStatus(String fulfillmentStatus) { this.fulfillmentStatus = fulfillmentStatus; }
    public String getFulfillmentNote() { return fulfillmentNote; }
    public void setFulfillmentNote(String fulfillmentNote) { this.fulfillmentNote = fulfillmentNote; }
    public Date getFulfillmentUpdatedAt() { return fulfillmentUpdatedAt; }
    public void setFulfillmentUpdatedAt(Date fulfillmentUpdatedAt) { this.fulfillmentUpdatedAt = fulfillmentUpdatedAt; }
    public String getApplicationKey() { return applicationKey; }
    public void setApplicationKey(String applicationKey) { this.applicationKey = applicationKey; }
    public String getOpenScopeKey() { return openScopeKey; }
    public void setOpenScopeKey(String openScopeKey) { this.openScopeKey = openScopeKey; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
    public String getRequestFingerprint() { return requestFingerprint; }
    public void setRequestFingerprint(String requestFingerprint) { this.requestFingerprint = requestFingerprint; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
    public Date getCancelledAt() { return cancelledAt; }
    public void setCancelledAt(Date cancelledAt) { this.cancelledAt = cancelledAt; }
    public String getReviewedBy() { return reviewedBy; }
    public void setReviewedBy(String reviewedBy) { this.reviewedBy = reviewedBy; }
    public Date getReviewedAt() { return reviewedAt; }
    public void setReviewedAt(Date reviewedAt) { this.reviewedAt = reviewedAt; }
}
