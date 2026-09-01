package com.macro.mall.operations.domain;

import java.util.Date;

/**
 * Internal row used by the authorized operations reviewer. It deliberately
 * stays separate from the HTTP view because member identity and audit fields
 * are needed for transactional review, but not for the review screen.
 */
public class AiAfterSalesReviewRecord {
    private Long id;
    private Long memberId;
    private String orderSn;
    private String applicationType;
    private String productName;
    private String productAttr;
    private String reason;
    private String description;
    private String status;
    private String statusNote;
    private String fulfillmentStatus;
    private String fulfillmentNote;
    private Date createTime;
    private Date updateTime;
    private String reviewedBy;
    private Date reviewedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getMemberId() { return memberId; }
    public void setMemberId(Long memberId) { this.memberId = memberId; }
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
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getStatusNote() { return statusNote; }
    public void setStatusNote(String statusNote) { this.statusNote = statusNote; }
    public String getFulfillmentStatus() { return fulfillmentStatus; }
    public void setFulfillmentStatus(String fulfillmentStatus) { this.fulfillmentStatus = fulfillmentStatus; }
    public String getFulfillmentNote() { return fulfillmentNote; }
    public void setFulfillmentNote(String fulfillmentNote) { this.fulfillmentNote = fulfillmentNote; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
    public String getReviewedBy() { return reviewedBy; }
    public void setReviewedBy(String reviewedBy) { this.reviewedBy = reviewedBy; }
    public Date getReviewedAt() { return reviewedAt; }
    public void setReviewedAt(Date reviewedAt) { this.reviewedAt = reviewedAt; }
}
