package com.macro.mall.portal.component;

import com.macro.mall.portal.domain.QueueEnum;
import com.macro.mall.portal.service.OmsPortalOrderService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.MessagePostProcessor;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class CancelOrderReceiverTest {

    @Mock
    private OmsPortalOrderService portalOrderService;

    @Mock
    private AmqpTemplate amqpTemplate;

    @InjectMocks
    private CancelOrderReceiver receiver;

    @Test
    void shouldMoveCancellationFailureToFailureQueueAndAckOriginalMessage() {
        doThrow(new RuntimeException("locked stock is inconsistent"))
                .when(portalOrderService).cancelOrder(42L);

        receiver.handle(42L);

        verify(amqpTemplate).convertAndSend(
                eq(QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getExchange()),
                eq(QueueEnum.QUEUE_ORDER_CANCEL_FAILURE.getRouteKey()),
                eq(42L),
                any(MessagePostProcessor.class));
    }

    @Test
    void shouldRejectWithoutRequeueWhenFailureQueueIsUnavailable() {
        doThrow(new RuntimeException("locked stock is inconsistent"))
                .when(portalOrderService).cancelOrder(42L);
        doThrow(new RuntimeException("broker unavailable"))
                .when(amqpTemplate)
                .convertAndSend(anyString(), anyString(), any(), any(MessagePostProcessor.class));

        assertThrows(AmqpRejectAndDontRequeueException.class, () -> receiver.handle(42L));
    }

    @Test
    void shouldNotPublishFailureForSuccessfulCancellation() {
        receiver.handle(42L);

        verify(portalOrderService).cancelOrder(42L);
        verifyNoInteractions(amqpTemplate);
    }
}
