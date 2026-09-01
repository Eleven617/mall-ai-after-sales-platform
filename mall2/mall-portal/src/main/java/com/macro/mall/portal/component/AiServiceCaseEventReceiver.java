package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiServiceCaseEventDeliveryDao;
import com.macro.mall.portal.domain.AiServiceCaseEventDelivery;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Date;

/**
 * An idempotent receipt of case-state notification events.  It deliberately
 * does not mutate the case state, so duplicate or out-of-order messages can
 * never overwrite Java's transactional state machine.
 */
@Component
public class AiServiceCaseEventReceiver {
    private final AiServiceCaseEventDeliveryDao deliveryDao;

    @Autowired
    public AiServiceCaseEventReceiver(AiServiceCaseEventDeliveryDao deliveryDao) {
        this.deliveryDao = deliveryDao;
    }

    @RabbitListener(queues = "mall.service-case.status")
    public void handle(Message message) {
        if (message == null || message.getMessageProperties() == null) {
            throw reject("人工协同事件缺少消息属性");
        }
        String eventId = header(message, "event_id", "[a-f0-9-]{8,64}");
        String caseId = header(message, "case_id", "[a-f0-9-]{36}");
        header(message, "event_type", "service_case_[a-z_]{3,64}");
        AiServiceCaseEventDelivery delivery = new AiServiceCaseEventDelivery();
        delivery.setEventId(eventId);
        delivery.setCaseId(caseId);
        delivery.setDeliveryStatus("DELIVERED");
        delivery.setReceivedAt(new Date());
        deliveryDao.insertIgnore(delivery);
    }

    private String header(Message message, String name, String pattern) {
        Object value = message.getMessageProperties().getHeaders().get(name);
        String normalized = value == null ? "" : String.valueOf(value).trim();
        if (!normalized.matches(pattern)) {
            throw reject("人工协同事件字段不合法: " + name);
        }
        return normalized;
    }

    private AmqpRejectAndDontRequeueException reject(String message) {
        return new AmqpRejectAndDontRequeueException(message);
    }
}
