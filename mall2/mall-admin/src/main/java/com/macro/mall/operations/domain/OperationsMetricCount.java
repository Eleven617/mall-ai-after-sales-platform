package com.macro.mall.operations.domain;

/** A non-identifying aggregation row returned by the operations DAO. */
public class OperationsMetricCount {
    private String metricKey;
    private Long total;

    public String getMetricKey() { return metricKey; }
    public void setMetricKey(String metricKey) { this.metricKey = metricKey; }
    public Long getTotal() { return total; }
    public void setTotal(Long total) { this.total = total; }
}
