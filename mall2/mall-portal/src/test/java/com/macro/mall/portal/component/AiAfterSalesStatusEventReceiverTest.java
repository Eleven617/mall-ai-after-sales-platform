package com.macro.mall.portal.component;

import com.macro.mall.portal.dao.AiAfterSalesEventDeliveryDao;
import com.macro.mall.portal.domain.AiAfterSalesEventDelivery;
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
class AiAfterSalesStatusEventReceiverTest {
    @Mock
    private AiAfterSalesEventDeliveryDao deliveryDao;

    private AiAfterSalesStatusEventReceiver receiver;

    @BeforeEach
    void setUp() {
        receiver = new AiAfterSalesStatusEventReceiver(deliveryDao);
    }

    @Test
    void shouldRecordDeliveryBeforeListenerAcknowledgesMessage() {
        when(deliveryDao.insertIgnore(any(AiAfterSalesEventDelivery.class))).thenReturn(1);

        receiver.handle(validMessage());

        ArgumentCaptor<AiAfterSalesEventDelivery> captor =
                ArgumentCaptor.forClass(AiAfterSalesEventDelivery.class);
        verify(deliveryDao).insertIgnore(captor.capture());
        assertThat(captor.getValue().getEventId()).isEqualTo("event-11");
        assertThat(captor.getValue().getApplicationId()).isEqualTo(701L);
        assertThat(captor.getValue().getDeliveryStatus()).isEqualTo("DELIVERED");
    }

    @Test
    void shouldTreatBrokerRedeliveryAsAnIdempotentNoOp() {
        when(deliveryDao.insertIgnore(any(AiAfterSalesEventDelivery.class))).thenReturn(0);

        receiver.handle(validMessage());

        verify(deliveryDao).insertIgnore(any(AiAfterSalesEventDelivery.class));
    }

    @Test
    void shouldRejectMalformedMessageWithoutRequeue() {
        MessageProperties properties = new MessageProperties();
        properties.setHeader("event_id", "event-11");
        properties.setHeader("event_type", "after_sales_application_created");

        assertThatThrownBy(() -> receiver.handle(new Message(new byte[0], properties)))
                .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    }

    @Test
    void shouldRejectLegacySourceAfterFinalUnifiedCutover() {
        MessageProperties properties = new MessageProperties();
        properties.setHeader("event_id", "event-legacy");
        properties.setHeader("application_id", 701L);
        properties.setHeader("application_source", "legacy_return");
        properties.setHeader("event_type", "after_sales_application_created");

        assertThatThrownBy(() -> receiver.handle(new Message(new byte[0], properties)))
                .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    }

    private Message validMessage() {
        MessageProperties properties = new MessageProperties();
        properties.setHeader("event_id", "event-11");
        properties.setHeader("application_id", 701L);
        properties.setHeader("application_source", "unified_after_sales");
        properties.setHeader("event_type", "after_sales_application_created");
        return new Message("{}".getBytes(), properties);
    }
}
