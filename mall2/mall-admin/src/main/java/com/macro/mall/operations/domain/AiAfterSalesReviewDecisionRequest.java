package com.macro.mall.operations.domain;

import io.swagger.annotations.ApiModelProperty;

/** A human reviewer can only accept or reject one still-pending request. */
public class AiAfterSalesReviewDecisionRequest {
    @ApiModelProperty("accept 或 reject")
    private String action;

    @ApiModelProperty("客户可见的处理说明；不能包含内部系统、个人信息或工具结果")
    private String note;

    public String getAction() { return action; }
    public void setAction(String action) { this.action = action; }
    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
}
