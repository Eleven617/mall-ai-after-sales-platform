package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiAfterSalesEventDeliveryDao;
import com.macro.mall.portal.domain.AiAfterSalesEventDelivery;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Date;

/**
 * Records a delivered after-sales status event before the listener returns.
 * RabbitMQ may redeliver, so the unique event-id insert is the consumer's
 * separate idempotency boundary.
 */
@Component
public class AiAfterSalesStatusEventReceiver {
    private static final Logger LOGGER = LoggerFactory.getLogger(AiAfterSalesStatusEventReceiver.class);
    private static final String EVENT_CREATED = "after_sales_application_created";
    private static final String EVENT_REVIEWED = "after_sales_application_reviewed";
    private static final String EVENT_CANCELLED = "after_sales_application_cancelled";
    private static final String EVENT_MODIFIED = "after_sales_application_modified";

    private final AiAfterSalesEventDeliveryDao deliveryDao;

    @Autowired
    public AiAfterSalesStatusEventReceiver(AiAfterSalesEventDeliveryDao deliveryDao) {
        this.deliveryDao = deliveryDao;
    }

    @RabbitListener(queues = "mall.after-sales.status")
    public void handle(Message message) {
        AiAfterSalesEventDelivery delivery = fromHeaders(message);
        int created = deliveryDao.insertIgnore(delivery);
        if (created == 1) {
            LOGGER.info("after-sales event delivery recorded, eventId={}, applicationId={}",
                    delivery.getEventId(), delivery.getApplicationId());
            return;
        }
        LOGGER.info("duplicate after-sales event ignored, eventId={}", delivery.getEventId());
    }

    private AiAfterSalesEventDelivery fromHeaders(Message message) {
        if (message == null || message.getMessageProperties() == null) {
            throw reject("after-sales event has no message properties");
        }
        Object eventIdHeader = message.getMessageProperties().getHeaders().get("event_id");
        Object applicationIdHeader = message.getMessageProperties().getHeaders().get("application_id");
        Object applicationSourceHeader = message.getMessageProperties().getHeaders().get("application_source");
        Object eventTypeHeader = message.getMessageProperties().getHeaders().get("event_type");
        String eventId = stringHeader(eventIdHeader, "event_id");
        String applicationSource = applicationSource(applicationSourceHeader);
        String eventType = stringHeader(eventTypeHeader, "event_type");
        if (!EVENT_CREATED.equals(eventType) && !EVENT_REVIEWED.equals(eventType)
                && !EVENT_CANCELLED.equals(eventType) && !EVENT_MODIFIED.equals(eventType)) {
            throw reject("unsupported after-sales event type");
        }
        Long applicationId;
        try {
            applicationId = Long.valueOf(stringHeader(applicationIdHeader, "application_id"));
        } catch (NumberFormatException error) {
            throw reject("invalid after-sales application id", error);
        }

        AiAfterSalesEventDelivery delivery = new AiAfterSalesEventDelivery();
        delivery.setEventId(eventId);
        delivery.setApplicationId(applicationId);
        delivery.setApplicationSource(applicationSource);
        delivery.setEventType(eventType);
        delivery.setDeliveryStatus("DELIVERED");
        delivery.setDeliveredAt(new Date());
        return delivery;
    }

    private String stringHeader(Object value, String name) {
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw reject("missing after-sales event " + name);
        }
        return String.valueOf(value).trim();
    }

    private String applicationSource(Object value) {
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw reject("missing after-sales application source");
        }
        String normalized = String.valueOf(value).trim();
        if ("unified_after_sales".equals(normalized)) {
            return normalized;
        }
        throw reject("unsupported after-sales application source");
    }

    private AmqpRejectAndDontRequeueException reject(String message) {
        return new AmqpRejectAndDontRequeueException(message);
    }

    private AmqpRejectAndDontRequeueException reject(String message, Exception cause) {
        return new AmqpRejectAndDontRequeueException(message, cause);
    }
}
