package com.macro.mall.operations.domain;

/** A Java-calculated category count and percentage for the selected window. */
public class AiOperationsHandoffCategorySummary {
    private String category;
    private Long count;
    private Double percentage;

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public Long getCount() { return count; }
    public void setCount(Long count) { this.count = count; }
    public Double getPercentage() { return percentage; }
    public void setPercentage(Double percentage) { this.percentage = percentage; }
}
