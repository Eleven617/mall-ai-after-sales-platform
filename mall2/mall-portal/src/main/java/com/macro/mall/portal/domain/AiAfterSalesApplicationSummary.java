package com.macro.mall.portal.domain;

import java.util.Date;

/** Customer-safe projection of one unified after-sales application. */
public class AiAfterSalesApplicationSummary {
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
    private Long createdAt;
    private Long updatedAt;
    private String handlingNote;
    private String fulfillmentStatus;
    private String fulfillmentStatusLabel;
    private String fulfillmentNote;
    private boolean canCancel;
    private boolean canModify;
    private boolean canSupplement;

    public static AiAfterSalesApplicationSummary from(AiAfterSalesApplicationRecord record) {
        AiAfterSalesApplicationSummary summary = new AiAfterSalesApplicationSummary();
        summary.setApplicationId(record.getId());
        summary.setOrderSn(record.getOrderSn());
        summary.setApplicationType(record.getApplicationType());
        AiAfterSalesApplicationType type = AiAfterSalesApplicationType.fromValue(record.getApplicationType());
        summary.setApplicationTypeLabel(type == null ? "售后申请" : type.getLabel());
        summary.setProductName(normalize(record.getProductName()));
        summary.setProductAttr(normalize(record.getProductAttr()));
        summary.setReason(firstNonBlank(record.getReason(), "未说明"));
        summary.setDescription(normalize(record.getDescription()));
        AiAfterSalesApplicationStatus status = AiAfterSalesApplicationStatus
                .fromDatabaseValue(record.getStatus());
        summary.setStatus(status == null ? "unknown" : status.getPublicValue());
        summary.setStatusLabel(status == null ? "状态待确认" : status.getLabel());
        summary.setCreatedAt(toEpochMillis(record.getCreateTime()));
        summary.setUpdatedAt(toEpochMillis(record.getUpdateTime()));
        summary.setHandlingNote(normalize(record.getStatusNote()));
        AiAfterSalesFulfillmentStatus fulfillment = AiAfterSalesFulfillmentStatus
                .fromDatabaseValue(record.getFulfillmentStatus());
        summary.setFulfillmentStatus(fulfillment == null ? "unknown" : fulfillment.getPublicValue());
        summary.setFulfillmentStatusLabel(fulfillment == null ? "履约状态待确认" : fulfillment.getLabel());
        summary.setFulfillmentNote(normalize(record.getFulfillmentNote()));
        boolean mutable = status == AiAfterSalesApplicationStatus.PENDING_REVIEW;
        summary.setCanCancel(mutable);
        summary.setCanModify(mutable);
        summary.setCanSupplement(
                status == AiAfterSalesApplicationStatus.ACCEPTED
                        && fulfillment != AiAfterSalesFulfillmentStatus.SUCCEEDED
        );
        return summary;
    }

    private static String firstNonBlank(String first, String fallback) {
        String normalized = normalize(first);
        return normalized == null ? fallback : normalized;
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static Long toEpochMillis(Date value) {
        return value == null ? null : value.getTime();
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
    public Long getCreatedAt() { return createdAt; }
    public void setCreatedAt(Long createdAt) { this.createdAt = createdAt; }
    public Long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Long updatedAt) { this.updatedAt = updatedAt; }
    public String getHandlingNote() { return handlingNote; }
    public void setHandlingNote(String handlingNote) { this.handlingNote = handlingNote; }
    public String getFulfillmentStatus() { return fulfillmentStatus; }
    public void setFulfillmentStatus(String fulfillmentStatus) { this.fulfillmentStatus = fulfillmentStatus; }
    public String getFulfillmentStatusLabel() { return fulfillmentStatusLabel; }
    public void setFulfillmentStatusLabel(String fulfillmentStatusLabel) { this.fulfillmentStatusLabel = fulfillmentStatusLabel; }
    public String getFulfillmentNote() { return fulfillmentNote; }
    public void setFulfillmentNote(String fulfillmentNote) { this.fulfillmentNote = fulfillmentNote; }
    public boolean isCanCancel() { return canCancel; }
    public void setCanCancel(boolean canCancel) { this.canCancel = canCancel; }
    public boolean isCanModify() { return canModify; }
    public void setCanModify(boolean canModify) { this.canModify = canModify; }
    public boolean isCanSupplement() { return canSupplement; }
    public void setCanSupplement(boolean canSupplement) { this.canSupplement = canSupplement; }
}
