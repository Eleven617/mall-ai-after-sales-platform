package com.macro.mall.operations.domain;

/** Internal DAO row for the de-identified handoff overview query. */
public class OperationsHandoffCategoryCount {
    private String metricKey;
    private Long total;

    public String getMetricKey() { return metricKey; }
    public void setMetricKey(String metricKey) { this.metricKey = metricKey; }
    public Long getTotal() { return total; }
    public void setTotal(Long total) { this.total = total; }
}
