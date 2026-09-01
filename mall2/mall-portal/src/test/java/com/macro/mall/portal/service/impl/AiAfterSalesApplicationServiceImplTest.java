package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.ApiException;
import com.macro.mall.mapper.OmsOrderItemMapper;
import com.macro.mall.mapper.OmsOrderMapper;
import com.macro.mall.model.OmsOrder;
import com.macro.mall.model.OmsOrderItem;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiAfterSalesApplicationDao;
import com.macro.mall.portal.dao.AiAfterSalesActionDao;
import com.macro.mall.portal.dao.AiAfterSalesFulfillmentCallbackDao;
import com.macro.mall.portal.dao.AiAfterSalesOutboxDao;
import com.macro.mall.portal.domain.AiAfterSalesApplicationRecord;
import com.macro.mall.portal.domain.AiAfterSalesActionRecord;
import com.macro.mall.portal.domain.AiAfterSalesActionRequest;
import com.macro.mall.portal.domain.AiAfterSalesApplicationSummary;
import com.macro.mall.portal.domain.AiAfterSalesApplyRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilityRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilitySummary;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRecord;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesOutboxEvent;
import com.macro.mall.portal.service.OmsPortalOrderService;
import com.macro.mall.portal.service.UmsMemberService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiAfterSalesApplicationServiceImplTest {
    @InjectMocks
    private AiAfterSalesApplicationServiceImpl service;

    @Mock
    private UmsMemberService memberService;
    @Mock
    private OmsOrderMapper orderMapper;
    @Mock
    private OmsOrderItemMapper orderItemMapper;
    @Mock
    private AiAfterSalesApplicationDao applicationDao;
    @Mock
    private AiAfterSalesActionDao actionDao;
    @Mock
    private AiAfterSalesFulfillmentCallbackDao fulfillmentCallbackDao;
    @Mock
    private AiAfterSalesOutboxDao outboxDao;
    @Mock
    private OmsPortalOrderService portalOrderService;

    @Test
    void shouldCreatePendingExchangeFromCurrentMembersOwnedItem() {
        UmsMember member = member(7L);
        OmsOrder order = order(101L, 7L, 2);
        OmsOrderItem item = item(501L, 101L, "无线耳机", "颜色：黑色");
        AiAfterSalesApplicationRecord persisted = persisted(
                801L, 7L, order, item, "exchange", "PENDING_REVIEW", request("exchange")
        );
        when(memberService.getCurrentMember()).thenReturn(member);
        when(orderMapper.selectByExample(any())).thenReturn(Collections.singletonList(order));
        when(orderItemMapper.selectByExample(any())).thenReturn(Collections.singletonList(item));
        when(applicationDao.findByMemberIdAndIdempotencyKey(7L, key()))
                .thenReturn(null, persisted);
        when(applicationDao.insertIgnore(any(AiAfterSalesApplicationRecord.class))).thenReturn(1);
        when(outboxDao.insert(any(AiAfterSalesOutboxEvent.class))).thenReturn(1);

        AiAfterSalesApplicationSummary created = service.createForAi(request("exchange"));

        assertThat(created.getApplicationId()).isEqualTo(801L);
        assertThat(created.getApplicationType()).isEqualTo("exchange");
        assertThat(created.getStatus()).isEqualTo("pending_review");
        ArgumentCaptor<AiAfterSalesApplicationRecord> recordCaptor =
                ArgumentCaptor.forClass(AiAfterSalesApplicationRecord.class);
        verify(applicationDao).insertIgnore(recordCaptor.capture());
        assertThat(recordCaptor.getValue().getOrderId()).isEqualTo(101L);
        assertThat(recordCaptor.getValue().getOrderItemId()).isEqualTo(501L);
        assertThat(recordCaptor.getValue().getProductName()).isEqualTo("无线耳机");
        assertThat(recordCaptor.getValue().getOpenScopeKey()).isEqualTo("7:101:501:exchange");
        ArgumentCaptor<AiAfterSalesOutboxEvent> eventCaptor =
                ArgumentCaptor.forClass(AiAfterSalesOutboxEvent.class);
        verify(outboxDao).insert(eventCaptor.capture());
        assertThat(eventCaptor.getValue().getApplicationId()).isEqualTo(801L);
        assertThat(eventCaptor.getValue().getMemberId()).isEqualTo(7L);
        assertThat(eventCaptor.getValue().getApplicationSource()).isEqualTo("unified_after_sales");
        assertThat(eventCaptor.getValue().getEventType()).isEqualTo("after_sales_application_created");
    }

    @Test
    void shouldOnlyPermitReturnRefundAfterItemSelection() {
        UmsMember member = member(7L);
        OmsOrder order = order(101L, 7L, 2);
        when(memberService.getCurrentMember()).thenReturn(member);
        when(orderMapper.selectByExample(any())).thenReturn(Collections.singletonList(order));

        AiAfterSalesEligibilityRequest request = new AiAfterSalesEligibilityRequest();
        request.setOrderSn(order.getOrderSn());
        request.setApplicationType("return_refund");

        AiAfterSalesEligibilitySummary eligibility = service.checkEligibility(request);

        assertThat(eligibility.isEligible()).isFalse();
        assertThat(eligibility.isRequiresProductSelection()).isTrue();
        assertThat(eligibility.getDecision()).isEqualTo("needs_product_selection");
        verify(orderItemMapper, never()).selectByExample(any());
    }

    @Test
    void shouldCancelOnlyUnpaidOrderAfterExplicitConfirmedSubmission() {
        UmsMember member = member(7L);
        OmsOrder pendingPaymentOrder = order(101L, 7L, 0);
        OmsOrder closedOrder = order(101L, 7L, 4);
        AiAfterSalesApplicationRecord persisted = persisted(
                803L, 7L, pendingPaymentOrder, null, "cancel_refund", "COMPLETED", request("cancel_refund")
        );
        persisted.setProductName("整笔订单");
        persisted.setStatusNote("未支付订单已取消");
        when(memberService.getCurrentMember()).thenReturn(member);
        when(orderMapper.selectByExample(any())).thenReturn(Collections.singletonList(pendingPaymentOrder));
        when(orderMapper.selectByPrimaryKey(101L)).thenReturn(closedOrder);
        when(applicationDao.findByMemberIdAndIdempotencyKey(7L, key()))
                .thenReturn(null, persisted);
        when(applicationDao.insertIgnore(any(AiAfterSalesApplicationRecord.class))).thenReturn(1);
        when(outboxDao.insert(any(AiAfterSalesOutboxEvent.class))).thenReturn(1);

        AiAfterSalesApplicationSummary created = service.createForAi(request("cancel_refund"));

        assertThat(created.getStatus()).isEqualTo("completed");
        assertThat(created.getHandlingNote()).isEqualTo("未支付订单已取消");
        verify(portalOrderService).cancelOrder(101L);
        verify(orderItemMapper, never()).selectByExample(any());
    }

    @Test
    void shouldRejectShippedOrderCancellationRatherThanPretendingRefund() {
        UmsMember member = member(7L);
        OmsOrder shippedOrder = order(101L, 7L, 2);
        when(memberService.getCurrentMember()).thenReturn(member);
        when(orderMapper.selectByExample(any())).thenReturn(Collections.singletonList(shippedOrder));
        when(applicationDao.findByMemberIdAndIdempotencyKey(7L, key())).thenReturn(null);

        assertThatThrownBy(() -> service.createForAi(request("cancel_refund")))
                .isInstanceOf(ApiException.class)
                .hasMessageContaining("不能提交取消退款申请");
        verifyNoInteractions(orderItemMapper, outboxDao, portalOrderService);
    }

    @Test
    void shouldReplaySameIdempotencyKeyButRejectChangedConfirmedContent() {
        UmsMember member = member(7L);
        AiAfterSalesApplyRequest request = request("repair");
        AiAfterSalesApplicationRecord replay = persisted(
                805L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "repair", "PENDING_REVIEW", request
        );
        when(memberService.getCurrentMember()).thenReturn(member);
        when(applicationDao.findByMemberIdAndIdempotencyKey(7L, key())).thenReturn(replay);

        AiAfterSalesApplicationSummary same = service.createForAi(request);
        assertThat(same.getApplicationId()).isEqualTo(805L);

        request.setReason("另一个原因");
        assertThatThrownBy(() -> service.createForAi(request))
                .isInstanceOf(ApiException.class)
                .hasMessage("该售后提交标识与原确认内容不一致！");
        verifyNoInteractions(orderMapper, orderItemMapper, outboxDao, portalOrderService);
    }

    @Test
    void shouldOnlyCancelPendingRequestOwnedByCurrentMember() {
        UmsMember member = member(7L);
        AiAfterSalesApplicationRecord cancelled = persisted(
                809L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "repair", "CANCELLED", request("repair")
        );
        cancelled.setStatusNote("客户已取消申请");
        when(memberService.getCurrentMember()).thenReturn(member);
        AiAfterSalesActionRequest action = actionRequest("cancel", 809L, null, null);
        when(actionDao.findByMemberIdAndActionId(7L, action.getActionId())).thenReturn(null);
        when(actionDao.insertIgnore(any())).thenReturn(1);
        when(applicationDao.cancelPending(809L, 7L)).thenReturn(1);
        when(applicationDao.findByIdAndMemberId(809L, 7L)).thenReturn(cancelled);
        when(outboxDao.insert(any(AiAfterSalesOutboxEvent.class))).thenReturn(1);

        AiAfterSalesApplicationSummary summary = service.cancelForAiCurrentMember(809L, action);

        assertThat(summary.getStatus()).isEqualTo("cancelled");
        assertThat(summary.isCanCancel()).isFalse();
        assertThat(summary.isCanModify()).isFalse();
        verify(applicationDao).cancelPending(809L, 7L);
    }

    @Test
    void shouldAllowAcceptedApplicationToReceiveSupplementButNotChangeReason() {
        UmsMember member = member(7L);
        AiAfterSalesApplicationRecord accepted = persisted(
                811L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "repair", "ACCEPTED", request("repair")
        );
        accepted.setFulfillmentStatus("PROCESSING");
        AiAfterSalesApplicationRecord supplemented = persisted(
                811L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "repair", "ACCEPTED", request("repair")
        );
        supplemented.setFulfillmentStatus("PROCESSING");
        supplemented.setCustomerSupplement("请安排人工检查充电故障");
        AiAfterSalesActionRequest action = actionRequest(
                "modify", 811L, null, "请安排人工检查充电故障"
        );
        when(memberService.getCurrentMember()).thenReturn(member);
        when(actionDao.findByMemberIdAndActionId(7L, action.getActionId())).thenReturn(null);
        when(applicationDao.findByIdAndMemberId(811L, 7L)).thenReturn(accepted, supplemented);
        when(applicationDao.supplementAccepted(811L, 7L, "请安排人工检查充电故障"))
                .thenReturn(1);
        when(actionDao.insertIgnore(any(AiAfterSalesActionRecord.class))).thenReturn(1);
        when(outboxDao.insert(any(AiAfterSalesOutboxEvent.class))).thenReturn(1);

        AiAfterSalesApplicationSummary summary = service.modifyForAiCurrentMember(811L, action);

        assertThat(summary.isCanSupplement()).isTrue();
        verify(applicationDao).supplementAccepted(811L, 7L, "请安排人工检查充电故障");
        verify(applicationDao, never()).modifyPending(anyLong(), anyLong(), any(), any());
    }

    @Test
    void shouldRecordOneIdempotentFulfillmentCallbackAndExposeOnlyActualState() {
        AiAfterSalesApplicationRecord accepted = persisted(
                821L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "return_refund", "ACCEPTED", request("return_refund")
        );
        accepted.setFulfillmentStatus("NOT_STARTED");
        AiAfterSalesApplicationRecord completed = persisted(
                821L, 7L, order(101L, 7L, 2), item(501L, 101L, "无线耳机", null),
                "return_refund", "COMPLETED", request("return_refund")
        );
        completed.setFulfillmentStatus("SUCCEEDED");
        completed.setFulfillmentNote("演示适配器回执（仅测试/演示，不代表真实外部系统）。");
        AiAfterSalesFulfillmentCallbackRequest callback = callbackRequest(
                821L, "demo-callback-821", "succeeded", "demo_adapter"
        );
        when(fulfillmentCallbackDao.findByCallbackEventId("demo-callback-821")).thenReturn(null);
        when(applicationDao.findById(821L)).thenReturn(accepted, completed);
        when(fulfillmentCallbackDao.insertIgnore(any(AiAfterSalesFulfillmentCallbackRecord.class)))
                .thenReturn(1);
        when(applicationDao.updateFulfillmentFromCallback(
                821L, "COMPLETED", "SUCCEEDED", callback.getNote()
        )).thenReturn(1);

        AiAfterSalesApplicationSummary summary = service.recordFulfillmentCallback(callback);

        assertThat(summary.getStatus()).isEqualTo("completed");
        assertThat(summary.getFulfillmentStatus()).isEqualTo("succeeded");
        verify(fulfillmentCallbackDao).insertIgnore(any(AiAfterSalesFulfillmentCallbackRecord.class));
        verify(applicationDao).updateFulfillmentFromCallback(
                821L, "COMPLETED", "SUCCEEDED", callback.getNote()
        );
    }

    private UmsMember member(Long id) {
        UmsMember member = new UmsMember();
        member.setId(id);
        return member;
    }

    private OmsOrder order(Long id, Long memberId, Integer status) {
        OmsOrder order = new OmsOrder();
        order.setId(id);
        order.setMemberId(memberId);
        order.setOrderSn("202608210001");
        order.setStatus(status);
        order.setDeleteStatus(0);
        return order;
    }

    private OmsOrderItem item(Long id, Long orderId, String name, String attr) {
        OmsOrderItem item = new OmsOrderItem();
        item.setId(id);
        item.setOrderId(orderId);
        item.setProductName(name);
        item.setProductAttr(attr);
        return item;
    }

    private AiAfterSalesApplyRequest request(String type) {
        AiAfterSalesApplyRequest request = new AiAfterSalesApplyRequest();
        request.setOrderSn("202608210001");
        request.setApplicationType(type);
        request.setOrderItemId("cancel_refund".equals(type) ? null : 501L);
        request.setReason("商品存在质量问题");
        request.setDescription("耳机无法充电");
        request.setIdempotencyKey(key());
        return request;
    }

    private AiAfterSalesApplicationRecord persisted(
            Long id,
            Long memberId,
            OmsOrder order,
            OmsOrderItem item,
            String type,
            String status,
            AiAfterSalesApplyRequest request
    ) {
        AiAfterSalesApplicationRecord record = new AiAfterSalesApplicationRecord();
        record.setId(id);
        record.setMemberId(memberId);
        record.setOrderId(order.getId());
        record.setOrderItemId(item == null ? null : item.getId());
        record.setOrderSn(order.getOrderSn());
        record.setApplicationType(type);
        record.setProductName(item == null ? "整笔订单" : item.getProductName());
        record.setProductAttr(item == null ? null : item.getProductAttr());
        record.setReason(request.getReason());
        record.setDescription(request.getDescription());
        record.setStatus(status);
        record.setIdempotencyKey(key());
        record.setRequestFingerprint(fingerprint(request, type));
        return record;
    }

    private String fingerprint(AiAfterSalesApplyRequest request, String type) {
        String canonical = request.getOrderSn().trim() + "\n"
                + type + "\n"
                + (request.getOrderItemId() == null ? "" : request.getOrderItemId()) + "\n"
                + request.getReason().trim() + "\n"
                + request.getDescription().trim();
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(bytes.length * 2);
            for (byte value : bytes) {
                result.append(String.format("%02x", value));
            }
            return result.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private String key() {
        return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    }

    private AiAfterSalesActionRequest actionRequest(
            String action, Long applicationId, String reason, String description
    ) {
        AiAfterSalesActionRequest request = new AiAfterSalesActionRequest();
        request.setActionId(key());
        request.setReason(reason);
        request.setDescription(description);
        request.setContentHash(hash(action + "\n" + applicationId + "\n"
                + (reason == null ? "" : reason) + "\n"
                + (description == null ? "" : description)));
        return request;
    }

    private AiAfterSalesFulfillmentCallbackRequest callbackRequest(
            Long applicationId, String eventId, String fulfillmentStatus, String source
    ) {
        AiAfterSalesFulfillmentCallbackRequest request = new AiAfterSalesFulfillmentCallbackRequest();
        request.setApplicationId(applicationId);
        request.setCallbackEventId(eventId);
        request.setFulfillmentStatus(fulfillmentStatus);
        request.setSource(source);
        request.setNote("演示适配器回执（仅测试/演示，不代表真实外部系统）。");
        return request;
    }

    private String hash(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(bytes.length * 2);
            for (byte item : bytes) result.append(String.format("%02x", item));
            return result.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
