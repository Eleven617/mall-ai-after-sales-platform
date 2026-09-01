package com.macro.mall.portal.controller;

import com.macro.mall.portal.domain.AiAfterSalesApplicationSummary;
import com.macro.mall.portal.domain.AiAfterSalesActionRequest;
import com.macro.mall.portal.domain.AiAfterSalesApplyRequest;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.service.AiAfterSalesApplicationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiAfterSalesApplicationControllerTest {
    private static final String SERVICE_KEY = "after-sales-test-key";

    @InjectMocks
    private AiAfterSalesApplicationController controller;

    @Mock
    private AiAfterSalesApplicationService applicationService;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(controller, "serviceKey", SERVICE_KEY);
    }

    @Test
    void shouldRequireInternalCapabilityForEveryAfterSalesWrite() {
        assertThatThrownBy(() -> controller.create(null, new AiAfterSalesApplyRequest()))
                .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> controller.cancel(101L, "wrong-key", new AiAfterSalesActionRequest()))
                .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> controller.modify(
                101L, null, new AiAfterSalesActionRequest()
        )).isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> controller.fulfillmentCallback(
                "wrong-key", new AiAfterSalesFulfillmentCallbackRequest()
        )).isInstanceOf(AccessDeniedException.class);

        verifyNoInteractions(applicationService);
    }

    @Test
    void shouldForwardConfirmedWriteOnlyWhenCapabilityMatches() {
        AiAfterSalesApplicationSummary summary = new AiAfterSalesApplicationSummary();
        summary.setApplicationId(101L);
        when(applicationService.createForAi(any(AiAfterSalesApplyRequest.class)))
                .thenReturn(summary);

        AiAfterSalesApplicationSummary result = controller
                .create(SERVICE_KEY, new AiAfterSalesApplyRequest())
                .getData();

        assertThat(result.getApplicationId()).isEqualTo(101L);
        verify(applicationService).createForAi(any(AiAfterSalesApplyRequest.class));
    }
}
