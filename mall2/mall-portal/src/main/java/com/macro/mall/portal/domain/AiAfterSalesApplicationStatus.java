package com.macro.mall.portal.domain;

/**
 * Stored lifecycle states for the unified after-sales request itself.
 * They intentionally do not claim payment, carrier, warehouse, or repair
 * fulfillment states that this project has no upstream contract for.
 */
public enum AiAfterSalesApplicationStatus {
    PENDING_REVIEW("PENDING_REVIEW", "pending_review", "待审核"),
    ACCEPTED("ACCEPTED", "accepted", "已受理"),
    COMPLETED("COMPLETED", "completed", "已完成"),
    REJECTED("REJECTED", "rejected", "已拒绝"),
    CANCELLED("CANCELLED", "cancelled", "已取消");

    private final String databaseValue;
    private final String publicValue;
    private final String label;

    AiAfterSalesApplicationStatus(
            String databaseValue,
            String publicValue,
            String label
    ) {
        this.databaseValue = databaseValue;
        this.publicValue = publicValue;
        this.label = label;
    }

    public String getDatabaseValue() {
        return databaseValue;
    }

    public String getPublicValue() {
        return publicValue;
    }

    public String getLabel() {
        return label;
    }

    public static AiAfterSalesApplicationStatus fromDatabaseValue(String value) {
        if (value == null) {
            return null;
        }
        for (AiAfterSalesApplicationStatus status : values()) {
            if (status.databaseValue.equals(value.trim())) {
                return status;
            }
        }
        return null;
    }
}
