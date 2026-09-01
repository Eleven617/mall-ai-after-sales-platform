package com.macro.mall.operations.domain;

import java.util.ArrayList;
import java.util.List;

/**
 * Privacy-safe, deduplicated human-handoff aggregate. It contains no member,
 * case key, order or raw customer content.
 */
public class AiOperationsHandoffOverview {
    private Integer windowDays;
    private String windowStart;
    private String windowEnd;
    private Long totalUniqueHandoffs;
    private List<AiOperationsHandoffCategorySummary> categories = new ArrayList<>();

    public Integer getWindowDays() { return windowDays; }
    public void setWindowDays(Integer windowDays) { this.windowDays = windowDays; }
    public String getWindowStart() { return windowStart; }
    public void setWindowStart(String windowStart) { this.windowStart = windowStart; }
    public String getWindowEnd() { return windowEnd; }
    public void setWindowEnd(String windowEnd) { this.windowEnd = windowEnd; }
    public Long getTotalUniqueHandoffs() { return totalUniqueHandoffs; }
    public void setTotalUniqueHandoffs(Long totalUniqueHandoffs) { this.totalUniqueHandoffs = totalUniqueHandoffs; }
    public List<AiOperationsHandoffCategorySummary> getCategories() { return categories; }
    public void setCategories(List<AiOperationsHandoffCategorySummary> categories) { this.categories = categories; }
}
