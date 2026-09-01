package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiServiceCaseOutboxDao;
import com.macro.mall.portal.domain.AiServiceCaseOutboxEvent;
import com.macro.mall.portal.domain.QueueEnum;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.core.Message;
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
class AiServiceCaseOutboxPublisherTest {
    @Mock
    private AiServiceCaseOutboxDao outboxDao;
    @Mock
    private RabbitTemplate rabbitTemplate;
    private AiServiceCaseOutboxPublisher publisher;

    @BeforeEach
    void setUp() {
        publisher = new AiServiceCaseOutboxPublisher(outboxDao, rabbitTemplate);
    }

    @Test
    void shouldPublishOnlyOpaqueCaseReferencesAfterBrokerConfirmation() {
        AiServiceCaseOutboxEvent event = event(0);
        when(outboxDao.findReadyForPublishing(20)).thenReturn(Collections.singletonList(event));
        when(outboxDao.claimForPublishing(eq(11L), anyLong())).thenReturn(1);
        when(outboxDao.markPublished(11L)).thenReturn(1);
        doAnswer(invocation -> {
            CorrelationData correlation = invocation.getArgument(3);
            correlation.getFuture().set(new CorrelationData.Confirm(true, null));
            return null;
        }).when(rabbitTemplate).send(anyString(), anyString(), any(Message.class), any(CorrelationData.class));

        publisher.publishPendingEvents();

        ArgumentCaptor<Message> messageCaptor = ArgumentCaptor.forClass(Message.class);
        verify(rabbitTemplate).send(
                eq(QueueEnum.QUEUE_SERVICE_CASE_STATUS.getExchange()),
                eq(QueueEnum.QUEUE_SERVICE_CASE_STATUS.getRouteKey()),
                messageCaptor.capture(), any(CorrelationData.class)
        );
        String body = new String(messageCaptor.getValue().getBody(), StandardCharsets.UTF_8);
        assertThat(messageCaptor.getValue().getMessageProperties().getHeaders())
                .containsEntry("event_id", event.getEventId())
                .containsEntry("case_id", event.getCaseId())
                .doesNotContainKey("member_id");
        assertThat(body).contains(event.getEventId()).contains(event.getCaseId()).doesNotContain("member_id");
        verify(outboxDao).markPublished(11L);
    }

    @Test
    void shouldRetryThenMarkTerminalFailureWithBoundedAttempts() {
        AiServiceCaseOutboxEvent retryable = event(0);
        when(outboxDao.findReadyForPublishing(20)).thenReturn(Collections.singletonList(retryable));
        when(outboxDao.claimForPublishing(eq(11L), anyLong())).thenReturn(1);
        doThrow(new RuntimeException("RabbitMQ unavailable")).when(rabbitTemplate).send(
                anyString(), anyString(), any(Message.class), any(CorrelationData.class)
        );
        publisher.publishPendingEvents();
        verify(outboxDao).markPublishFailure(eq(11L), eq("PENDING"), eq(1), eq("RabbitMQ unavailable"));

        AiServiceCaseOutboxEvent terminal = event(4);
        publisher.publishClaimedEvent(terminal);
        verify(outboxDao).markPublishFailure(eq(11L), eq("FAILED"), isNull(), eq("RabbitMQ unavailable"));
    }

    private AiServiceCaseOutboxEvent event(int attempts) {
        AiServiceCaseOutboxEvent event = new AiServiceCaseOutboxEvent();
        event.setId(11L);
        event.setEventId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        event.setCaseId("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
        event.setMemberId(7L);
        event.setEventType("service_case_claimed");
        event.setStateVersion(2);
        event.setAttemptCount(attempts);
        event.setCreatedAt(new Date(1720000000000L));
        return event;
    }
}
