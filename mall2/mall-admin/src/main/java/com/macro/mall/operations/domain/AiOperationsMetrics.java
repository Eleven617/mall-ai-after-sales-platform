package com.macro.mall.operations.domain;

import java.util.LinkedHashMap;
import java.util.Map;

/** Privacy-safe aggregate facts that an Operations Analysis Agent may read. */
public class AiOperationsMetrics {
    private Integer windowDays;
    private Map<String, Long> afterSalesByStatus = new LinkedHashMap<>();
    private Map<String, Long> reasonCounts = new LinkedHashMap<>();
    private Map<String, Long> outboxByStatus = new LinkedHashMap<>();
    private Map<String, Long> deliveryByStatus = new LinkedHashMap<>();
    private AiOperationsHandoffOverview handoffOverview;

    public Integer getWindowDays() { return windowDays; }
    public void setWindowDays(Integer windowDays) { this.windowDays = windowDays; }
    public Map<String, Long> getAfterSalesByStatus() { return afterSalesByStatus; }
    public void setAfterSalesByStatus(Map<String, Long> afterSalesByStatus) { this.afterSalesByStatus = afterSalesByStatus; }
    public Map<String, Long> getReasonCounts() { return reasonCounts; }
    public void setReasonCounts(Map<String, Long> reasonCounts) { this.reasonCounts = reasonCounts; }
    public Map<String, Long> getOutboxByStatus() { return outboxByStatus; }
    public void setOutboxByStatus(Map<String, Long> outboxByStatus) { this.outboxByStatus = outboxByStatus; }
    public Map<String, Long> getDeliveryByStatus() { return deliveryByStatus; }
    public void setDeliveryByStatus(Map<String, Long> deliveryByStatus) { this.deliveryByStatus = deliveryByStatus; }
    public AiOperationsHandoffOverview getHandoffOverview() { return handoffOverview; }
    public void setHandoffOverview(AiOperationsHandoffOverview handoffOverview) { this.handoffOverview = handoffOverview; }
}
