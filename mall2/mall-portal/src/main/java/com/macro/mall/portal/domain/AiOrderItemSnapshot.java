package com.macro.mall.portal.domain;

import io.swagger.annotations.ApiModelProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * 给 AI 服务用于定位订单商品的最小订单项摘要。
 *
 * 内部订单项 ID 只用于后续受服务端校验的业务调用，不是用户需要输入的字段。
 */
@Getter
@Setter
public class AiOrderItemSnapshot {

    @ApiModelProperty("订单项ID")
    private Long orderItemId;

    @ApiModelProperty("商品名称")
    private String productName;

    @ApiModelProperty("商品规格")
    private String productAttr;

    @ApiModelProperty("购买数量")
    private Integer productQuantity;
}
