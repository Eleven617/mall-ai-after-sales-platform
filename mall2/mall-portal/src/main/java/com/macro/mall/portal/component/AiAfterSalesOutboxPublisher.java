package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiAfterSalesOutboxDao;
import com.macro.mall.portal.domain.AiAfterSalesOutboxEvent;
import com.macro.mall.portal.domain.QueueEnum;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Publishes only events that were committed to MySQL first. The row lease
 * makes a process crash recoverable, while the consumer owns broker-delivery
 * idempotency.
 */
@Component
public class AiAfterSalesOutboxPublisher {
    private static final Logger LOGGER = LoggerFactory.getLogger(AiAfterSalesOutboxPublisher.class);
    private static final String EVENT_FULFILLMENT_REQUESTED_PREFIX = "after_sales_fulfillment_requested:";

    private final AiAfterSalesOutboxDao outboxDao;
    private final RabbitTemplate rabbitTemplate;

    @Value("${after-sales.outbox.batch-size:20}")
    private int batchSize = 20;
    @Value("${after-sales.outbox.lease-ms:30000}")
    private long leaseMs = 30000L;
    @Value("${after-sales.outbox.confirm-timeout-ms:3000}")
    private long confirmTimeoutMs = 3000L;
    @Value("${after-sales.outbox.max-publish-attempts:5}")
    private int maxPublishAttempts = 5;

    @Autowired
    public AiAfterSalesOutboxPublisher(
            AiAfterSalesOutboxDao outboxDao,
            RabbitTemplate rabbitTemplate
    ) {
        this.outboxDao = outboxDao;
        this.rabbitTemplate = rabbitTemplate;
    }

    @Scheduled(fixedDelayString = "${after-sales.outbox.publish-fixed-delay-ms:2000}")
    public void publishPendingEvents() {
        List<AiAfterSalesOutboxEvent> events = outboxDao.findReadyForPublishing(batchSize);
        for (AiAfterSalesOutboxEvent event : events) {
            if (event == null || event.getId() == null) {
                continue;
            }
            long leaseSeconds = Math.max(1L, (leaseMs + 999L) / 1000L);
            if (outboxDao.claimForPublishing(event.getId(), leaseSeconds) != 1) {
                continue;
            }
            publishClaimedEvent(event);
        }
    }

    void publishClaimedEvent(AiAfterSalesOutboxEvent event) {
        try {
            sendAndAwaitBrokerConfirm(event);
            if (outboxDao.markPublished(event.getId()) != 1) {
                LOGGER.warn("after-sales outbox publish confirmation could not be persisted, eventId={}", event.getEventId());
            }
        } catch (Exception failure) {
            markPublishFailure(event, failure);
        }
    }

    private void sendAndAwaitBrokerConfirm(AiAfterSalesOutboxEvent event) throws Exception {
        CorrelationData correlationData = new CorrelationData(event.getEventId());
        QueueEnum destination = destinationFor(event);
        rabbitTemplate.send(
                destination.getExchange(),
                destination.getRouteKey(),
                toMessage(event),
                correlationData
        );
        CorrelationData.Confirm confirm = correlationData.getFuture()
                .get(confirmTimeoutMs, TimeUnit.MILLISECONDS);
        if (confirm == null || !confirm.isAck()) {
            String reason = confirm == null ? "missing publisher confirmation" : confirm.getReason();
            throw new IllegalStateException("RabbitMQ rejected after-sales event: " + safeError(reason));
        }
        if (correlationData.getReturned() != null) {
            throw new IllegalStateException("RabbitMQ returned after-sales event without a route");
        }
    }

    private QueueEnum destinationFor(AiAfterSalesOutboxEvent event) {
        return event.getEventType() != null
                && event.getEventType().startsWith(EVENT_FULFILLMENT_REQUESTED_PREFIX)
                ? QueueEnum.QUEUE_AFTER_SALES_FULFILLMENT
                : QueueEnum.QUEUE_AFTER_SALES_STATUS;
    }

    private Message toMessage(AiAfterSalesOutboxEvent event) {
        long occurredAt = event.getCreateTime() == null
                ? System.currentTimeMillis()
                : event.getCreateTime().getTime();
        String body = "{\"event_id\":\"" + event.getEventId()
                + "\",\"application_id\":" + event.getApplicationId()
                + ",\"application_source\":\"" + safeSource(event.getApplicationSource())
                + "\""
                + ",\"event_type\":\"" + event.getEventType()
                + "\",\"occurred_at\":" + occurredAt + "}";
        MessageProperties properties = new MessageProperties();
        properties.setContentType("application/json");
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        // A durable queue alone is not sufficient after a broker restart:
        // mark every domain event persistent explicitly as part of its contract.
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader("event_id", event.getEventId());
        properties.setHeader("application_id", event.getApplicationId());
        properties.setHeader("application_source", safeSource(event.getApplicationSource()));
        properties.setHeader("event_type", event.getEventType());
        properties.setHeader("occurred_at", occurredAt);
        return new Message(body.getBytes(StandardCharsets.UTF_8), properties);
    }

    private void markPublishFailure(AiAfterSalesOutboxEvent event, Exception failure) {
        int attemptedCount = (event.getAttemptCount() == null ? 0 : event.getAttemptCount()) + 1;
        boolean terminal = attemptedCount >= maxPublishAttempts;
        String status = terminal ? "FAILED" : "PENDING";
        Integer retryDelaySeconds = terminal ? null : Math.toIntExact(retryDelaySeconds(attemptedCount));
        outboxDao.markPublishFailure(
                event.getId(),
                status,
                retryDelaySeconds,
                safeError(failure.getMessage())
        );
        if (terminal) {
            LOGGER.error("after-sales event reached bounded publish failure state, eventId={}", event.getEventId(), failure);
        } else {
            LOGGER.warn("after-sales event publish failed; it remains retryable, eventId={}", event.getEventId(), failure);
        }
    }

    private long retryDelaySeconds(int attemptedCount) {
        int shift = Math.min(Math.max(attemptedCount - 1, 0), 5);
        return Math.min(30L, 1L << shift);
    }

    private String safeError(String value) {
        if (value == null || value.trim().isEmpty()) {
            return "publisher failure";
        }
        return value.length() <= 500 ? value : value.substring(0, 500);
    }

    private String safeSource(String value) {
        if ("unified_after_sales".equals(value)) {
            return value;
        }
        throw new IllegalArgumentException("unsupported unified after-sales event source");
    }
}
