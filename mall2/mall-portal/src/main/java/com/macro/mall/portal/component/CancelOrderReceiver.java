package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.QueueEnum;
import com.macro.mall.portal.service.OmsPortalOrderService;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.MessagePostProcessor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * 取消订单消息的接收者
 * Created by macro on 2018/9/14.
 */
@Component
@RabbitListener(queues = "mall.order.cancel")
public class CancelOrderReceiver {
    private static final Logger LOGGER = LoggerFactory.getLogger(CancelOrderReceiver.class);
    @Autowired
    private OmsPortalOrderService portalOrderService;
    @Autowired
    private AmqpTemplate amqpTemplate;
    @RabbitHandler
    public void handle(Long orderId){
        try {
            portalOrderService.cancelOrder(orderId);
            LOGGER.info("process orderId:{}",orderId);
        } catch (RuntimeException failure) {
            publishFailure(orderId, failure);
        }
    }

    private void publishFailure(Long orderId, RuntimeException failure) {
        try {
            MessagePostProcessor postProcessor = message -> {
                message.getMessageProperties().setHeader("failureReason", safeMessage(failure));
                return message;
            };
            amqpTemplate.convertAndSend(
                    QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getExchange(),
                    QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getRouteKey(),
                    orderId,
                    postProcessor);
            LOGGER.error("cancel order failed; moved to failure queue, orderId={}", orderId, failure);
        } catch (RuntimeException publishFailure) {
            LOGGER.error("cancel order failure queue is unavailable; reject without requeue, orderId={}",
                    orderId, publishFailure);
            throw new AmqpRejectAndDontRequeueException(
                    "Unable to publish failed cancellation to the failure queue", publishFailure);
        }
    }

    private String safeMessage(RuntimeException failure) {
        String message = failure.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return failure.getClass().getSimpleName();
        }
        return message.length() > 500 ? message.substring(0, 500) : message;
    }
}
