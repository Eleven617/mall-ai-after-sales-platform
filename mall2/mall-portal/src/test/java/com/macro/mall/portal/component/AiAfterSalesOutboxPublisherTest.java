package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiAfterSalesOutboxDao;
import com.macro.mall.portal.domain.AiAfterSalesOutboxEvent;
import com.macro.mall.portal.domain.QueueEnum;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiAfterSalesOutboxPublisherTest {
    @Mock
    private AiAfterSalesOutboxDao outboxDao;
    @Mock
    private RabbitTemplate rabbitTemplate;

    private AiAfterSalesOutboxPublisher publisher;

    @BeforeEach
    void setUp() {
        publisher = new AiAfterSalesOutboxPublisher(outboxDao, rabbitTemplate);
    }

    @Test
    void shouldMarkEventPublishedOnlyAfterBrokerAcknowledgesIt() {
        AiAfterSalesOutboxEvent event = pendingEvent(0);
        when(outboxDao.findReadyForPublishing(20)).thenReturn(Collections.singletonList(event));
        when(outboxDao.claimForPublishing(eq(11L), anyLong())).thenReturn(1);
        doAnswer(invocation -> {
            CorrelationData correlation = invocation.getArgument(3);
            correlation.getFuture().set(new CorrelationData.Confirm(true, null));
            return null;
        }).when(rabbitTemplate).send(
                eq(QueueEnum.QUEUE_AFTER_SALES_STATUS.getExchange()),
                eq(QueueEnum.QUEUE_AFTER_SALES_STATUS.getRouteKey()),
                any(Message.class),
                any(CorrelationData.class)
        );

        publisher.publishPendingEvents();

        ArgumentCaptor<Message> messageCaptor = ArgumentCaptor.forClass(Message.class);
        verify(rabbitTemplate).send(
                eq(QueueEnum.QUEUE_AFTER_SALES_STATUS.getExchange()),
                eq(QueueEnum.QUEUE_AFTER_SALES_STATUS.getRouteKey()),
                messageCaptor.capture(),
                any(CorrelationData.class)
        );
        assertThat(messageCaptor.getValue().getMessageProperties().getHeaders())
                .containsEntry("event_id", "event-11")
                .containsEntry("application_id", 701L)
                .containsEntry("event_type", "after_sales_application_created")
                .containsKey("occurred_at")
                .doesNotContainKey("member_id");
        assertThat(messageCaptor.getValue().getMessageProperties().getDeliveryMode())
                .isEqualTo(MessageDeliveryMode.PERSISTENT);
        assertThat(new String(messageCaptor.getValue().getBody(), StandardCharsets.UTF_8))
                .contains("event-11")
                .contains("701")
                .contains("occurred_at")
                .doesNotContain("member_id");
        verify(outboxDao).claimForPublishing(11L, 30L);
        verify(outboxDao).markPublished(11L);
    }

    @Test
    void shouldKeepFailedBrokerPublishRetryable() {
        AiAfterSalesOutboxEvent event = pendingEvent(0);
        when(outboxDao.findReadyForPublishing(20)).thenReturn(Collections.singletonList(event));
        when(outboxDao.claimForPublishing(eq(11L), anyLong())).thenReturn(1);
        doThrow(new RuntimeException("RabbitMQ unavailable")).when(rabbitTemplate).send(
                anyString(), anyString(), any(Message.class), any(CorrelationData.class)
        );

        publisher.publishPendingEvents();

        verify(outboxDao).markPublishFailure(
                eq(11L), eq("PENDING"), eq(1), eq("RabbitMQ unavailable")
        );
    }

    @Test
    void shouldStopAutomaticPublishingAfterBoundedAttempts() {
        AiAfterSalesOutboxEvent event = pendingEvent(4);
        when(outboxDao.findReadyForPublishing(20)).thenReturn(Collections.singletonList(event));
        when(outboxDao.claimForPublishing(eq(11L), anyLong())).thenReturn(1);
        doThrow(new RuntimeException("RabbitMQ unavailable")).when(rabbitTemplate).send(
                anyString(), anyString(), any(Message.class), any(CorrelationData.class)
        );

        publisher.publishPendingEvents();

        verify(outboxDao).markPublishFailure(
                eq(11L), eq("FAILED"), isNull(), eq("RabbitMQ unavailable")
        );
    }

    private AiAfterSalesOutboxEvent pendingEvent(int attemptCount) {
        AiAfterSalesOutboxEvent event = new AiAfterSalesOutboxEvent();
        event.setId(11L);
        event.setEventId("event-11");
        event.setApplicationId(701L);
        event.setMemberId(7L);
        event.setApplicationSource("unified_after_sales");
        event.setEventType("after_sales_application_created");
        event.setStatus("PENDING");
        event.setAttemptCount(attemptCount);
        event.setCreateTime(new Date(1720000000000L));
        return event;
    }
}
