package com.macro.mall.portal.domain;

import io.swagger.annotations.ApiModelProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * Minimal, untrusted intent supplied by the AI service after the customer
 * explicitly confirms. Java reloads ownership and product facts itself.
 */
@Getter
@Setter
public class AiAfterSalesApplyRequest {
    @ApiModelProperty("用户可见的订单编号")
    private String orderSn;

    @ApiModelProperty("申请类型：cancel_refund、return_refund、exchange、repair")
    private String applicationType;

    @ApiModelProperty("退货、换货、维修时必须来自已授权订单快照的订单项ID")
    private Long orderItemId;

    @ApiModelProperty("客户提供的申请原因")
    private String reason;

    @ApiModelProperty("客户补充说明")
    private String description;

    @ApiModelProperty("确认后由 AI 服务生成的 32 位十六进制幂等键")
    private String idempotencyKey;
}
