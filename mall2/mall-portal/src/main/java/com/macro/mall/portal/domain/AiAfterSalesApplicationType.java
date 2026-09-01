package com.macro.mall.portal.domain;

/**
 * The customer-facing after-sales kinds supported by the unified application
 * core. These are business intents, not fulfillment outcomes.
 */
public enum AiAfterSalesApplicationType {
    CANCEL_REFUND("cancel_refund", "取消退款", false),
    RETURN_REFUND("return_refund", "退货退款", true),
    EXCHANGE("exchange", "换货", true),
    REPAIR("repair", "维修/质保", true);

    private final String value;
    private final String label;
    private final boolean productRequired;

    AiAfterSalesApplicationType(String value, String label, boolean productRequired) {
        this.value = value;
        this.label = label;
        this.productRequired = productRequired;
    }

    public String getValue() {
        return value;
    }

    public String getLabel() {
        return label;
    }

    public boolean isProductRequired() {
        return productRequired;
    }

    public static AiAfterSalesApplicationType fromValue(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        for (AiAfterSalesApplicationType type : values()) {
            if (type.value.equals(normalized)) {
                return type;
            }
        }
        return null;
    }
}
