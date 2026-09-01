package com.macro.mall.operations.domain;

import java.util.Date;

/**
 * Narrow internal-review projection. It excludes member ID, database order
 * ID, idempotency keys and reviewer identity, while retaining the customer
 * narrative an authorized human needs to make a real decision.
 */
public class AiAfterSalesReviewView {
    private Long applicationId;
    private String orderSn;
    private String applicationType;
    private String applicationTypeLabel;
    private String productName;
    private String productAttr;
    private String reason;
    private String description;
    private String status;
    private String statusLabel;
    private String statusNote;
    private Date createdAt;
    private Date updatedAt;
    private boolean canReview;

    public static AiAfterSalesReviewView from(AiAfterSalesReviewRecord record) {
        AiAfterSalesReviewView view = new AiAfterSalesReviewView();
        view.setApplicationId(record.getId());
        view.setOrderSn(record.getOrderSn());
        view.setApplicationType(record.getApplicationType());
        view.setApplicationTypeLabel(typeLabel(record.getApplicationType()));
        view.setProductName(record.getProductName());
        view.setProductAttr(record.getProductAttr());
        view.setReason(record.getReason());
        view.setDescription(record.getDescription());
        view.setStatus(publicStatus(record.getStatus()));
        view.setStatusLabel(statusLabel(record.getStatus()));
        view.setStatusNote(record.getStatusNote());
        view.setCreatedAt(record.getCreateTime());
        view.setUpdatedAt(record.getUpdateTime());
        view.setCanReview("PENDING_REVIEW".equals(record.getStatus()));
        return view;
    }

    private static String typeLabel(String type) {
        if ("cancel_refund".equals(type)) return "取消退款";
        if ("return_refund".equals(type)) return "退货退款";
        if ("exchange".equals(type)) return "换货";
        if ("repair".equals(type)) return "维修/质保";
        return "售后申请";
    }

    private static String publicStatus(String status) {
        if ("PENDING_REVIEW".equals(status)) return "pending_review";
        if ("ACCEPTED".equals(status)) return "accepted";
        if ("COMPLETED".equals(status)) return "completed";
        if ("REJECTED".equals(status)) return "rejected";
        if ("CANCELLED".equals(status)) return "cancelled";
        return "unknown";
    }

    private static String statusLabel(String status) {
        if ("PENDING_REVIEW".equals(status)) return "待审核";
        if ("ACCEPTED".equals(status)) return "已受理";
        if ("COMPLETED".equals(status)) return "已完成";
        if ("REJECTED".equals(status)) return "已拒绝";
        if ("CANCELLED".equals(status)) return "已取消";
        return "状态待确认";
    }

    public Long getApplicationId() { return applicationId; }
    public void setApplicationId(Long applicationId) { this.applicationId = applicationId; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getApplicationType() { return applicationType; }
    public void setApplicationType(String applicationType) { this.applicationType = applicationType; }
    public String getApplicationTypeLabel() { return applicationTypeLabel; }
    public void setApplicationTypeLabel(String applicationTypeLabel) { this.applicationTypeLabel = applicationTypeLabel; }
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
    public String getStatusLabel() { return statusLabel; }
    public void setStatusLabel(String statusLabel) { this.statusLabel = statusLabel; }
    public String getStatusNote() { return statusNote; }
    public void setStatusNote(String statusNote) { this.statusNote = statusNote; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
    public boolean isCanReview() { return canReview; }
    public void setCanReview(boolean canReview) { this.canReview = canReview; }
}
