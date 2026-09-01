package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCommand;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * Receives a durable Outbox command and delegates to the configured adapter.
 * A redelivery is harmless because the adapter callback has its own unique
 * callback-event audit key.
 */
@Component
public class AiAfterSalesFulfillmentCommandReceiver {
    private static final String EVENT_FULFILLMENT_REQUESTED_PREFIX = "after_sales_fulfillment_requested:";
    private final AiAfterSalesFulfillmentAdapter fulfillmentAdapter;

    @Autowired
    public AiAfterSalesFulfillmentCommandReceiver(AiAfterSalesFulfillmentAdapter fulfillmentAdapter) {
        this.fulfillmentAdapter = fulfillmentAdapter;
    }

    @RabbitListener(queues = "mall.after-sales.fulfillment")
    public void handle(Message message) {
        fulfillmentAdapter.dispatch(fromHeaders(message));
    }

    private AiAfterSalesFulfillmentCommand fromHeaders(Message message) {
        if (message == null || message.getMessageProperties() == null) {
            throw reject("fulfillment command has no message properties");
        }
        Object eventIdHeader = message.getMessageProperties().getHeaders().get("event_id");
        Object applicationIdHeader = message.getMessageProperties().getHeaders().get("application_id");
        Object eventTypeHeader = message.getMessageProperties().getHeaders().get("event_type");
        String eventId = requiredHeader(eventIdHeader, "event_id");
        String eventType = requiredHeader(eventTypeHeader, "event_type");
        if (!eventType.startsWith(EVENT_FULFILLMENT_REQUESTED_PREFIX)
                || eventType.length() <= EVENT_FULFILLMENT_REQUESTED_PREFIX.length()) {
            throw reject("unsupported fulfillment command event type");
        }
        try {
            AiAfterSalesFulfillmentCommand command = new AiAfterSalesFulfillmentCommand();
            command.setEventId(eventId);
            command.setCommandType(eventType.substring(EVENT_FULFILLMENT_REQUESTED_PREFIX.length()));
            command.setApplicationId(Long.valueOf(requiredHeader(applicationIdHeader, "application_id")));
            if (command.getApplicationId() <= 0) throw new NumberFormatException("non-positive id");
            return command;
        } catch (NumberFormatException error) {
            throw reject("invalid fulfillment application id", error);
        }
    }

    private String requiredHeader(Object value, String name) {
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw reject("missing fulfillment command " + name);
        }
        return String.valueOf(value).trim();
    }

    private AmqpRejectAndDontRequeueException reject(String message) {
        return new AmqpRejectAndDontRequeueException(message);
    }

    private AmqpRejectAndDontRequeueException reject(String message, Exception cause) {
        return new AmqpRejectAndDontRequeueException(message, cause);
    }
}
