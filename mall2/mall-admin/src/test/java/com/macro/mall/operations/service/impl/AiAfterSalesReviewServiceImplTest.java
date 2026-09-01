package com.macro.mall.operations.service.impl;

import com.macro.mall.operations.dao.AiAfterSalesReviewDao;
import com.macro.mall.operations.domain.AiAfterSalesReviewRecord;
import com.macro.mall.operations.domain.AiAfterSalesReviewView;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiAfterSalesReviewServiceImplTest {
    @InjectMocks
    private AiAfterSalesReviewServiceImpl service;

    @Mock
    private AiAfterSalesReviewDao reviewDao;

    @Test
    void shouldAcceptPendingApplicationAndRecordFulfillmentCommand() {
        AiAfterSalesReviewRecord pending = record(101L, "PENDING_REVIEW");
        AiAfterSalesReviewRecord accepted = record(101L, "ACCEPTED");
        accepted.setStatusNote("申请已受理，后续处理进度会同步给您。");
        accepted.setReviewedBy("order-operator");
        when(reviewDao.findById(101L)).thenReturn(pending, accepted);
        when(reviewDao.reviewPending(
                101L,
                "ACCEPTED",
                "申请已受理，后续处理进度会同步给您。",
                "order-operator",
                "NOT_STARTED",
                "申请已受理，正在创建履约任务。"
        )).thenReturn(1);
        when(reviewDao.insertReviewEvent(
                anyString(), anyLong(), anyLong(), anyString(), anyString()
        )).thenReturn(1);

        AiAfterSalesReviewView view = service.reviewPending(
                101L,
                "accept",
                "申请已受理，后续处理进度会同步给您。",
                "order-operator"
        );

        assertThat(view.getStatus()).isEqualTo("accepted");
        assertThat(view.getStatusLabel()).isEqualTo("已受理");
        assertThat(view.isCanReview()).isFalse();

        ArgumentCaptor<String> sourceCaptor = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<String> eventCaptor = ArgumentCaptor.forClass(String.class);
        verify(reviewDao).insertReviewEvent(
                anyString(), org.mockito.ArgumentMatchers.eq(101L),
                org.mockito.ArgumentMatchers.eq(7L),
                sourceCaptor.capture(), eventCaptor.capture()
        );
        assertThat(sourceCaptor.getValue()).isEqualTo("unified_after_sales");
        assertThat(eventCaptor.getValue())
                .isEqualTo("after_sales_fulfillment_requested:warehouse_receive_then_reship");
    }

    @Test
    void shouldRejectPendingApplication() {
        AiAfterSalesReviewRecord pending = record(102L, "PENDING_REVIEW");
        AiAfterSalesReviewRecord rejected = record(102L, "REJECTED");
        rejected.setStatusNote("当前申请不符合受理条件。");
        when(reviewDao.findById(102L)).thenReturn(pending, rejected);
        when(reviewDao.reviewPending(
                102L, "REJECTED", "当前申请不符合受理条件。", "order-operator",
                "NOT_STARTED", null
        )).thenReturn(1);
        when(reviewDao.insertReviewEvent(
                anyString(), anyLong(), anyLong(), anyString(), anyString()
        )).thenReturn(1);

        AiAfterSalesReviewView view = service.reviewPending(
                102L, "reject", "当前申请不符合受理条件。", "order-operator"
        );

        assertThat(view.getStatus()).isEqualTo("rejected");
        assertThat(view.getStatusLabel()).isEqualTo("已拒绝");
    }

    @Test
    void shouldRejectRepeatedReviewWithoutWritingAnything() {
        when(reviewDao.findById(103L)).thenReturn(record(103L, "ACCEPTED"));

        assertThatThrownBy(() -> service.reviewPending(
                103L, "accept", "申请已受理。", "order-operator"
        ))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("当前售后申请已不处于待审核状态");

        verify(reviewDao, never()).reviewPending(
                anyLong(), anyString(), anyString(), anyString(), anyString(), any()
        );
        verify(reviewDao, never()).insertReviewEvent(
                anyString(), anyLong(), anyLong(), anyString(), anyString()
        );
    }

    private AiAfterSalesReviewRecord record(Long id, String status) {
        AiAfterSalesReviewRecord record = new AiAfterSalesReviewRecord();
        record.setId(id);
        record.setMemberId(7L);
        record.setOrderSn("202608210001");
        record.setApplicationType("exchange");
        record.setProductName("无线耳机");
        record.setReason("商品存在质量问题");
        record.setDescription("耳机无法充电");
        record.setStatus(status);
        return record;
    }
}
