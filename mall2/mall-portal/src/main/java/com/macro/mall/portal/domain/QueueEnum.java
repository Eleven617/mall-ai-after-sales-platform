package com.macro.mall.portal.domain;

import lombok.Getter;

/**
 * 消息队列枚举类
 * Created by macro on 2018/9/14.
 */
@Getter
public enum QueueEnum {
    /**
     * 消息通知队列
     */
    QUEUE_ORDER_CANCEL("mall.order.direct", "mall.order.cancel", "mall.order.cancel"),
    /**
     * 消息通知ttl队列
     */
    QUEUE_TTL_ORDER_CANCEL("mall.order.direct.ttl", "mall.order.cancel.ttl", "mall.order.cancel.ttl"),
    QUEUE_ORDER_CANCEL_FAILURE("mall.order.direct.failure", "mall.order.cancel.failure", "mall.order.cancel.failure"),
    QUEUE_AFTER_SALES_STATUS("mall.after-sales.direct", "mall.after-sales.status", "mall.after-sales.status"),
    QUEUE_AFTER_SALES_STATUS_FAILURE("mall.after-sales.direct.failure", "mall.after-sales.status.failure", "mall.after-sales.status.failure"),
    /** A command for a configured fulfillment adapter; never a fake success. */
    QUEUE_AFTER_SALES_FULFILLMENT("mall.after-sales.fulfillment.direct", "mall.after-sales.fulfillment", "mall.after-sales.fulfillment"),
    QUEUE_AFTER_SALES_FULFILLMENT_FAILURE("mall.after-sales.fulfillment.direct.failure", "mall.after-sales.fulfillment.failure", "mall.after-sales.fulfillment.failure"),
    /** Human-collaboration status events contain only opaque case references. */
    QUEUE_SERVICE_CASE_STATUS("mall.service-case.direct", "mall.service-case.status", "mall.service-case.status"),
    QUEUE_SERVICE_CASE_STATUS_FAILURE("mall.service-case.direct.failure", "mall.service-case.status.failure", "mall.service-case.status.failure");

    /**
     * 交换名称
     */
    private final String exchange;
    /**
     * 队列名称
     */
    private final String name;
    /**
     * 路由键
     */
    private final String routeKey;

    QueueEnum(String exchange, String name, String routeKey) {
        this.exchange = exchange;
        this.name = name;
        this.routeKey = routeKey;
    }
}
