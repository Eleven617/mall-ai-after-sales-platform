package com.macro.mall.portal.config;

import com.macro.mall.portal.domain.QueueEnum;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ declarations for order cancellation and failure handling.
 */
@Configuration
public class RabbitMqConfig {

    @Bean
    DirectExchange orderDirect() {
        return new DirectExchange(QueueEnum.QUEUE_ORDER_CANCEL.getExchange(), true, false);
    }

    @Bean
    DirectExchange orderTtlDirect() {
        return new DirectExchange(QueueEnum.QUEUE_TTL_ORDER_CANCEL.getExchange(), true, false);
    }

    @Bean
    DirectExchange orderCancelFailureDirect() {
        return new DirectExchange(QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getExchange(), true, false);
    }

    @Bean
    DirectExchange afterSalesStatusDirect() {
        return new DirectExchange(QueueEnum.QUEUE_AFTER_SALES_STATUS.getExchange(), true, false);
    }

    @Bean
    DirectExchange afterSalesStatusFailureDirect() {
        return new DirectExchange(QueueEnum.QUEUE_AFTER_SALES_STATUS_FAILURE.getExchange(), true, false);
    }

    @Bean
    DirectExchange afterSalesFulfillmentDirect() {
        return new DirectExchange(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT.getExchange(), true, false);
    }

    @Bean
    DirectExchange afterSalesFulfillmentFailureDirect() {
        return new DirectExchange(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT_FAILURE.getExchange(), true, false);
    }

    @Bean
    DirectExchange serviceCaseStatusDirect() {
        return new DirectExchange(QueueEnum.QUEUE_SERVICE_CASE_STATUS.getExchange(), true, false);
    }

    @Bean
    DirectExchange serviceCaseStatusFailureDirect() {
        return new DirectExchange(QueueEnum.QUEUE_SERVICE_CASE_STATUS_FAILURE.getExchange(), true, false);
    }

    @Bean
    public Queue orderQueue() {
        return new Queue(QueueEnum.QUEUE_ORDER_CANCEL.getName(), true);
    }

    @Bean
    public Queue orderTtlQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_TTL_ORDER_CANCEL.getName())
                .withArgument("x-dead-letter-exchange", QueueEnum.QUEUE_ORDER_CANCEL.getExchange())
                .withArgument("x-dead-letter-routing-key", QueueEnum.QUEUE_ORDER_CANCEL.getRouteKey())
                .build();
    }

    @Bean
    public Queue orderCancelFailureQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getName())
                .withArgument("x-max-length", 1000)
                .withArgument("x-message-ttl", 604800000)
                .build();
    }

    @Bean
    public Queue afterSalesStatusQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_AFTER_SALES_STATUS.getName())
                .withArgument("x-dead-letter-exchange", QueueEnum.QUEUE_AFTER_SALES_STATUS_FAILURE.getExchange())
                .withArgument("x-dead-letter-routing-key", QueueEnum.QUEUE_AFTER_SALES_STATUS_FAILURE.getRouteKey())
                .build();
    }

    @Bean
    public Queue afterSalesStatusFailureQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_AFTER_SALES_STATUS_FAILURE.getName())
                .withArgument("x-max-length", 1000)
                .withArgument("x-message-ttl", 604800000)
                .build();
    }

    @Bean
    public Queue afterSalesFulfillmentQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT.getName())
                .withArgument("x-dead-letter-exchange", QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT_FAILURE.getExchange())
                .withArgument("x-dead-letter-routing-key", QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT_FAILURE.getRouteKey())
                .build();
    }

    @Bean
    public Queue afterSalesFulfillmentFailureQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT_FAILURE.getName())
                .withArgument("x-max-length", 1000)
                .withArgument("x-message-ttl", 604800000)
                .build();
    }

    @Bean
    public Queue serviceCaseStatusQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_SERVICE_CASE_STATUS.getName())
                .withArgument("x-dead-letter-exchange", QueueEnum.QUEUE_SERVICE_CASE_STATUS_FAILURE.getExchange())
                .withArgument("x-dead-letter-routing-key", QueueEnum.QUEUE_SERVICE_CASE_STATUS_FAILURE.getRouteKey())
                .build();
    }

    @Bean
    public Queue serviceCaseStatusFailureQueue() {
        return QueueBuilder
                .durable(QueueEnum.QUEUE_SERVICE_CASE_STATUS_FAILURE.getName())
                .withArgument("x-max-length", 1000)
                .withArgument("x-message-ttl", 604800000)
                .build();
    }

    @Bean
    Binding orderBinding(DirectExchange orderDirect, Queue orderQueue) {
        return BindingBuilder
                .bind(orderQueue)
                .to(orderDirect)
                .with(QueueEnum.QUEUE_ORDER_CANCEL.getRouteKey());
    }

    @Bean
    Binding orderTtlBinding(DirectExchange orderTtlDirect, Queue orderTtlQueue) {
        return BindingBuilder
                .bind(orderTtlQueue)
                .to(orderTtlDirect)
                .with(QueueEnum.QUEUE_TTL_ORDER_CANCEL.getRouteKey());
    }

    @Bean
    Binding orderCancelFailureBinding(DirectExchange orderCancelFailureDirect,
                                      Queue orderCancelFailureQueue) {
        return BindingBuilder
                .bind(orderCancelFailureQueue)
                .to(orderCancelFailureDirect)
                .with(QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getRouteKey());
    }

    @Bean
    Binding afterSalesStatusBinding(DirectExchange afterSalesStatusDirect,
                                    Queue afterSalesStatusQueue) {
        return BindingBuilder
                .bind(afterSalesStatusQueue)
                .to(afterSalesStatusDirect)
                .with(QueueEnum.QUEUE_AFTER_SALES_STATUS.getRouteKey());
    }

    @Bean
    Binding afterSalesStatusFailureBinding(DirectExchange afterSalesStatusFailureDirect,
                                           Queue afterSalesStatusFailureQueue) {
        return BindingBuilder
                .bind(afterSalesStatusFailureQueue)
                .to(afterSalesStatusFailureDirect)
                .with(QueueEnum.QUEUE_AFTER_SALES_STATUS_FAILURE.getRouteKey());
    }

    @Bean
    Binding afterSalesFulfillmentBinding(DirectExchange afterSalesFulfillmentDirect,
                                         Queue afterSalesFulfillmentQueue) {
        return BindingBuilder
                .bind(afterSalesFulfillmentQueue)
                .to(afterSalesFulfillmentDirect)
                .with(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT.getRouteKey());
    }

    @Bean
    Binding afterSalesFulfillmentFailureBinding(DirectExchange afterSalesFulfillmentFailureDirect,
                                                Queue afterSalesFulfillmentFailureQueue) {
        return BindingBuilder
                .bind(afterSalesFulfillmentFailureQueue)
                .to(afterSalesFulfillmentFailureDirect)
                .with(QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT_FAILURE.getRouteKey());
    }

    @Bean
    Binding serviceCaseStatusBinding(DirectExchange serviceCaseStatusDirect, Queue serviceCaseStatusQueue) {
        return BindingBuilder
                .bind(serviceCaseStatusQueue)
                .to(serviceCaseStatusDirect)
                .with(QueueEnum.QUEUE_SERVICE_CASE_STATUS.getRouteKey());
    }

    @Bean
    Binding serviceCaseStatusFailureBinding(
            DirectExchange serviceCaseStatusFailureDirect,
            Queue serviceCaseStatusFailureQueue
    ) {
        return BindingBuilder
                .bind(serviceCaseStatusFailureQueue)
                .to(serviceCaseStatusFailureDirect)
                .with(QueueEnum.QUEUE_SERVICE_CASE_STATUS_FAILURE.getRouteKey());
    }
}
