package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiServiceCaseOutboxDao;
import com.macro.mall.portal.domain.AiServiceCaseOutboxEvent;
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
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Publishes only committed human-collaboration transitions.  A broker outage
 * leaves the authoritative case state intact and the outbox row retryable.
 */
@Component
public class AiServiceCaseOutboxPublisher {
    private static final Logger LOGGER = LoggerFactory.getLogger(AiServiceCaseOutboxPublisher.class);

    private final AiServiceCaseOutboxDao outboxDao;
    private final RabbitTemplate rabbitTemplate;

    @Value("${service-case.outbox.batch-size:20}")
    private int batchSize = 20;
    @Value("${service-case.outbox.lease-ms:30000}")
    private long leaseMs = 30000L;
    @Value("${service-case.outbox.confirm-timeout-ms:3000}")
    private long confirmTimeoutMs = 3000L;
    @Value("${service-case.outbox.max-publish-attempts:5}")
    private int maxPublishAttempts = 5;

    @Autowired
    public AiServiceCaseOutboxPublisher(AiServiceCaseOutboxDao outboxDao, RabbitTemplate rabbitTemplate) {
        this.outboxDao = outboxDao;
        this.rabbitTemplate = rabbitTemplate;
    }

    @Scheduled(fixedDelayString = "${service-case.outbox.publish-fixed-delay-ms:2000}")
    public void publishPendingEvents() {
        List<AiServiceCaseOutboxEvent> events = outboxDao.findReadyForPublishing(batchSize);
        for (AiServiceCaseOutboxEvent event : events) {
            if (event == null || event.getId() == null) {
                continue;
            }
            long leaseSeconds = Math.max(1L, (leaseMs + 999L) / 1000L);
            if (outboxDao.claimForPublishing(event.getId(), leaseSeconds) == 1) {
                publishClaimedEvent(event);
            }
        }
    }

    void publishClaimedEvent(AiServiceCaseOutboxEvent event) {
        try {
            CorrelationData correlation = new CorrelationData(event.getEventId());
            rabbitTemplate.send(
                    QueueEnum.QUEUE_SERVICE_CASE_STATUS.getExchange(),
                    QueueEnum.QUEUE_SERVICE_CASE_STATUS.getRouteKey(),
                    toMessage(event),
                    correlation
            );
            CorrelationData.Confirm confirm = correlation.getFuture()
                    .get(confirmTimeoutMs, TimeUnit.MILLISECONDS);
            if (confirm == null || !confirm.isAck() || correlation.getReturned() != null) {
                throw new IllegalStateException("RabbitMQ 未确认人工协同状态事件");
            }
            if (outboxDao.markPublished(event.getId()) != 1) {
                LOGGER.warn("service-case outbox publish confirmation could not be persisted, eventId={}", event.getEventId());
            }
        } catch (Exception failure) {
            markFailure(event, failure);
        }
    }

    private Message toMessage(AiServiceCaseOutboxEvent event) {
        if (event.getEventId() == null || event.getCaseId() == null || event.getEventType() == null
                || !event.getEventType().matches("service_case_[a-z_]{3,64}")) {
            throw new IllegalArgumentException("人工协同事件契约不合法");
        }
        long occurredAt = event.getCreatedAt() == null ? System.currentTimeMillis() : event.getCreatedAt().getTime();
        String body = "{\"event_id\":\"" + event.getEventId() + "\",\"case_id\":\""
                + event.getCaseId() + "\",\"event_type\":\"" + event.getEventType()
                + "\",\"state_version\":" + event.getStateVersion() + ",\"occurred_at\":" + occurredAt + "}";
        MessageProperties properties = new MessageProperties();
        properties.setContentType("application/json");
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setHeader("event_id", event.getEventId());
        properties.setHeader("case_id", event.getCaseId());
        properties.setHeader("event_type", event.getEventType());
        properties.setHeader("state_version", event.getStateVersion());
        properties.setHeader("occurred_at", occurredAt);
        if (event.getCorrelationRef() != null) {
            properties.setHeader("correlation_ref", event.getCorrelationRef());
        }
        return new Message(body.getBytes(StandardCharsets.UTF_8), properties);
    }

    private void markFailure(AiServiceCaseOutboxEvent event, Exception failure) {
        int attempted = (event.getAttemptCount() == null ? 0 : event.getAttemptCount()) + 1;
        boolean terminal = attempted >= maxPublishAttempts;
        outboxDao.markPublishFailure(
                event.getId(), terminal ? "FAILED" : "PENDING",
                terminal ? null : Math.toIntExact(retryDelaySeconds(attempted)), safeError(failure.getMessage())
        );
        if (terminal) {
            LOGGER.error("service-case event reached bounded publish failure state, eventId={}", event.getEventId());
        } else {
            LOGGER.warn("service-case event publish failed; it remains retryable, eventId={}", event.getEventId());
        }
    }

    private long retryDelaySeconds(int attempted) {
        return Math.min(30L, 1L << Math.min(Math.max(attempted - 1, 0), 5));
    }

    private String safeError(String value) {
        if (value == null || value.trim().isEmpty()) {
            return "publisher failure";
        }
        return value.length() <= 500 ? value : value.substring(0, 500);
    }
}
