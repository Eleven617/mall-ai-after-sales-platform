package com.macro.mall.portal.domain;

/**
 * Fulfillment is intentionally separate from the customer application's
 * review lifecycle.  These values describe only work that a real adapter or a
 * controlled manual path has reported; they never infer a refund or shipment.
 */
public enum AiAfterSalesFulfillmentStatus {
    NOT_STARTED("NOT_STARTED", "not_started", "待履约"),
    PROCESSING("PROCESSING", "processing", "履约处理中"),
    SUCCEEDED("SUCCEEDED", "succeeded", "履约成功"),
    FAILED("FAILED", "failed", "履约失败"),
    MANUAL_REQUIRED("MANUAL_REQUIRED", "manual_required", "待人工履约");

    private final String databaseValue;
    private final String publicValue;
    private final String label;

    AiAfterSalesFulfillmentStatus(String databaseValue, String publicValue, String label) {
        this.databaseValue = databaseValue;
        this.publicValue = publicValue;
        this.label = label;
    }

    public String getDatabaseValue() { return databaseValue; }
    public String getPublicValue() { return publicValue; }
    public String getLabel() { return label; }

    public static AiAfterSalesFulfillmentStatus fromDatabaseValue(String value) {
        if (value == null) return null;
        for (AiAfterSalesFulfillmentStatus item : values()) {
            if (item.databaseValue.equals(value.trim())) return item;
        }
        return null;
    }

    public static AiAfterSalesFulfillmentStatus fromPublicValue(String value) {
        if (value == null) return null;
        for (AiAfterSalesFulfillmentStatus item : values()) {
            if (item.publicValue.equals(value.trim())) return item;
        }
        return null;
    }
}
