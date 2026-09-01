package com.macro.mall.operations.service.impl;

import com.macro.mall.operations.dao.AiOperationsDao;
import com.macro.mall.operations.domain.AiOperationsMetrics;
import com.macro.mall.operations.domain.OperationsHandoffCategoryCount;
import com.macro.mall.operations.domain.OperationsMetricCount;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Arrays;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiOperationsServiceImplTest {
    @InjectMocks
    private AiOperationsServiceImpl service;
    @Mock
    private AiOperationsDao dao;

    @Test
    void shouldReturnOnlyAggregateMetricsForAllowedWindow() {
        when(dao.countAfterSalesByStatus(any())).thenReturn(Arrays.asList(count("pending_review", 3L)));
        when(dao.countReasons(any())).thenReturn(Arrays.asList(count("质量问题", 2L)));
        when(dao.countOutboxByStatus(any())).thenReturn(Collections.singletonList(count("PENDING", 1L)));
        when(dao.countDeliveryByStatus(any())).thenReturn(Collections.singletonList(count("DELIVERED", 4L)));
        when(dao.countUniqueHandoffs(any(), any())).thenReturn(4L);
        when(dao.countUniqueHandoffsByCategory(any(), any())).thenReturn(Arrays.asList(
                handoffCount("delivery_exception", 3L),
                handoffCount("other_pending_classification", 1L)
        ));

        AiOperationsMetrics metrics = service.getMetrics(7);

        assertThat(metrics.getWindowDays()).isEqualTo(7);
        assertThat(metrics.getAfterSalesByStatus()).containsEntry("pending_review", 3L);
        assertThat(metrics.getReasonCounts()).containsEntry("质量问题", 2L);
        assertThat(metrics.getOutboxByStatus()).containsEntry("PENDING", 1L);
        assertThat(metrics.getHandoffOverview().getTotalUniqueHandoffs()).isEqualTo(4L);
        assertThat(metrics.getHandoffOverview().getCategories())
                .anySatisfy(item -> {
                    assertThat(item.getCategory()).isEqualTo("delivery_exception");
                    assertThat(item.getCount()).isEqualTo(3L);
                    assertThat(item.getPercentage()).isEqualTo(75D);
                })
                .anySatisfy(item -> {
                    assertThat(item.getCategory()).isEqualTo("other_pending_classification");
                    assertThat(item.getCount()).isEqualTo(1L);
                    assertThat(item.getPercentage()).isEqualTo(25D);
                });
        assertThat(java.util.Arrays.stream(AiOperationsMetrics.class.getDeclaredFields())
                .map(java.lang.reflect.Field::getName))
                .doesNotContain("memberId", "orderSn", "phone", "address", "description");
    }

    @Test
    void shouldRejectUnboundedAggregationWindow() {
        assertThatThrownBy(() -> service.getMetrics(365))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("仅支持 7 或 30 天运营聚合窗口");
    }

    private OperationsMetricCount count(String key, Long value) {
        OperationsMetricCount item = new OperationsMetricCount();
        item.setMetricKey(key);
        item.setTotal(value);
        return item;
    }

    private OperationsHandoffCategoryCount handoffCount(String key, Long value) {
        OperationsHandoffCategoryCount item = new OperationsHandoffCategoryCount();
        item.setMetricKey(key);
        item.setTotal(value);
        return item;
    }
}
