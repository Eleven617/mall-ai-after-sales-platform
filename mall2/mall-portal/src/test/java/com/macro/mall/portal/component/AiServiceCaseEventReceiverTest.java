package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiServiceCaseEventDeliveryDao;
import com.macro.mall.portal.domain.AiServiceCaseEventDelivery;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiServiceCaseEventReceiverTest {
    @Mock
    private AiServiceCaseEventDeliveryDao deliveryDao;
    private AiServiceCaseEventReceiver receiver;

    @BeforeEach
    void setUp() {
        receiver = new AiServiceCaseEventReceiver(deliveryDao);
    }

    @Test
    void shouldRecordOneIdempotentDeliveryWithoutMutatingCaseState() {
        when(deliveryDao.insertIgnore(any(AiServiceCaseEventDelivery.class))).thenReturn(1);
        receiver.handle(validMessage());
        receiver.handle(validMessage());

        ArgumentCaptor<AiServiceCaseEventDelivery> delivery = ArgumentCaptor.forClass(AiServiceCaseEventDelivery.class);
        verify(deliveryDao, org.mockito.Mockito.times(2)).insertIgnore(delivery.capture());
        assertThat(delivery.getValue().getEventId()).isEqualTo("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        assertThat(delivery.getValue().getCaseId()).isEqualTo("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
    }

    @Test
    void shouldRejectMalformedMessageWithoutInfiniteRequeue() {
        MessageProperties properties = new MessageProperties();
        properties.setHeader("event_id", "not-a-valid-identifier");
        properties.setHeader("case_id", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
        properties.setHeader("event_type", "service_case_claimed");
        assertThatThrownBy(() -> receiver.handle(new Message(new byte[0], properties)))
                .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    }

    private Message validMessage() {
        MessageProperties properties = new MessageProperties();
        properties.setHeader("event_id", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        properties.setHeader("case_id", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
        properties.setHeader("event_type", "service_case_claimed");
        return new Message("{}".getBytes(), properties);
    }
}
