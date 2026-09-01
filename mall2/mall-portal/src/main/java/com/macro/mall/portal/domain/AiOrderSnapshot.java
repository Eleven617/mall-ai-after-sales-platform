package com.macro.mall.portal.domain;

import io.swagger.annotations.ApiModelProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * 给 AI 服务使用的最小订单摘要。
 *
 * 不返回收货地址、联系电话、会员信息、支付金额等与客服问答无关的敏感字段。
 */
@Getter
@Setter
public class AiOrderSnapshot {

    @ApiModelProperty("订单编号")
    private String orderSn;

    @ApiModelProperty("订单状态码")
    private Integer status;

    @ApiModelProperty("订单状态说明")
    private String statusText;

    @ApiModelProperty("物流公司")
    private String deliveryCompany;

    @ApiModelProperty("物流单号")
    private String deliverySn;

    @ApiModelProperty("订单商品名称")
    private List<String> productNames;

    @ApiModelProperty("用于安全定位商品的订单项摘要")
    private List<AiOrderItemSnapshot> orderItems;
}
