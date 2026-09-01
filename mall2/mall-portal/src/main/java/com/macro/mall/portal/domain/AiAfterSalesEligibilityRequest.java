package com.macro.mall.portal.domain;

import io.swagger.annotations.ApiModelProperty;
import lombok.Getter;
import lombok.Setter;

/** Read-only eligibility query over Java-owned order facts. */
@Getter
@Setter
public class AiAfterSalesEligibilityRequest {
    @ApiModelProperty("用户可见的订单编号")
    private String orderSn;

    @ApiModelProperty("申请类型：cancel_refund、return_refund、exchange、repair")
    private String applicationType;

    @ApiModelProperty("若类型需要商品，使用当前订单中已验证的订单项ID")
    private Long orderItemId;
}
