package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.ApiException;
import com.macro.mall.mapper.OmsOrderItemMapper;
import com.macro.mall.mapper.OmsOrderMapper;
import com.macro.mall.mapper.OmsOrderSettingMapper;
import com.macro.mall.model.OmsOrder;
import com.macro.mall.model.OmsOrderItem;
import com.macro.mall.model.OmsOrderItemExample;
import com.macro.mall.model.OmsOrderSetting;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.domain.AiOrderSnapshot;
import com.macro.mall.portal.domain.OmsOrderDetail;
import com.macro.mall.portal.dao.PortalOrderDao;
import com.macro.mall.portal.service.UmsMemberService;
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
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OmsPortalOrderServiceImplTest {

    @InjectMocks
    private OmsPortalOrderServiceImpl orderService;

    @Mock
    private UmsMemberService memberService;

    @Mock
    private OmsOrderMapper orderMapper;

    @Mock
    private OmsOrderItemMapper orderItemMapper;

    @Mock
    private OmsOrderSettingMapper orderSettingMapper;

    @Mock
    private PortalOrderDao portalOrderDao;

    @Test
    void shouldReturnSanitizedSnapshotForCurrentMemberOrder() {
        UmsMember member = new UmsMember();
        member.setId(7L);

        OmsOrder order = new OmsOrder();
        order.setId(101L);
        order.setMemberId(7L);
        order.setOrderSn("202607240001");
        order.setStatus(2);
        order.setDeliveryCompany("顺丰速运");
        order.setDeliverySn("SF1234567890");
        order.setReceiverPhone("13800000000");

        OmsOrderItem item = new OmsOrderItem();
        item.setId(501L);
        item.setProductName("无线耳机");
        item.setProductAttr("颜色：黑色");
        item.setProductQuantity(2);

        when(memberService.getCurrentMember()).thenReturn(member);
        when(orderMapper.selectByExample(any())).thenReturn(Arrays.asList(order));
        when(orderItemMapper.selectByExample(any(OmsOrderItemExample.class)))
                .thenReturn(Arrays.asList(item));

        AiOrderSnapshot snapshot = orderService.getAiOrderSnapshotByOrderSn("202607240001");

        assertThat(snapshot.getOrderSn()).isEqualTo("202607240001");
        assertThat(snapshot.getStatusText()).isEqualTo("已发货");
        assertThat(snapshot.getDeliveryCompany()).isEqualTo("顺丰速运");
        assertThat(snapshot.getProductNames()).containsExactly("无线耳机");
        assertThat(snapshot.getOrderItems()).singleElement().satisfies(orderItem -> {
            assertThat(orderItem.getOrderItemId()).isEqualTo(501L);
            assertThat(orderItem.getProductName()).isEqualTo("无线耳机");
            assertThat(orderItem.getProductAttr()).isEqualTo("颜色：黑色");
            assertThat(orderItem.getProductQuantity()).isEqualTo(2);
        });
    }

    @Test
    void shouldRejectAnotherMembersOrder() {
        UmsMember currentMember = new UmsMember();
        currentMember.setId(7L);

        when(memberService.getCurrentMember()).thenReturn(currentMember);
        when(orderMapper.selectByExample(any())).thenReturn(Arrays.asList());

        assertThatThrownBy(() -> orderService.getAiOrderSnapshotByOrderSn("202607240001"))
                .isInstanceOf(ApiException.class)
                .hasMessage("订单不存在或无权访问！");
    }

    @Test
    void shouldReleaseTimeoutInventoryOnlyAfterWinningCancellationClaim() {
        OmsOrderDetail timeoutOrder = timeoutOrder(101L, 110L, 2);
        OmsOrderSetting setting = new OmsOrderSetting();
        setting.setNormalOrderOvertime(30);
        when(orderSettingMapper.selectByPrimaryKey(1L)).thenReturn(setting);
        when(portalOrderDao.getTimeOutOrders(30)).thenReturn(Collections.singletonList(timeoutOrder));
        when(portalOrderDao.markPendingOrderCancelled(101L)).thenReturn(1);
        when(portalOrderDao.releaseSkuStockLock(any())).thenReturn(1);

        assertThat(orderService.cancelTimeOutOrder()).isEqualTo(1);

        verify(portalOrderDao).markPendingOrderCancelled(101L);
        verify(portalOrderDao).releaseSkuStockLock(any());
    }

    @Test
    void shouldNotReleaseInventoryWhenAnotherWorkerAlreadyCancelledTimeoutOrder() {
        OmsOrderDetail timeoutOrder = timeoutOrder(101L, 110L, 2);
        OmsOrderSetting setting = new OmsOrderSetting();
        setting.setNormalOrderOvertime(30);
        when(orderSettingMapper.selectByPrimaryKey(1L)).thenReturn(setting);
        when(portalOrderDao.getTimeOutOrders(30)).thenReturn(Collections.singletonList(timeoutOrder));
        when(portalOrderDao.markPendingOrderCancelled(101L)).thenReturn(0);

        assertThat(orderService.cancelTimeOutOrder()).isZero();

        verify(portalOrderDao).markPendingOrderCancelled(101L);
        verify(portalOrderDao, never()).releaseSkuStockLock(any());
    }

    @Test
    void shouldTreatDuplicateBrokerCancellationAsNoOp() {
        when(portalOrderDao.markPendingOrderCancelled(101L)).thenReturn(0);

        orderService.cancelOrder(101L);

        verify(portalOrderDao).markPendingOrderCancelled(101L);
        verify(portalOrderDao, never()).releaseSkuStockLock(any());
        verify(orderMapper, never()).selectByPrimaryKey(anyLong());
    }

    private OmsOrderDetail timeoutOrder(Long orderId, Long skuId, Integer quantity) {
        OmsOrderItem item = new OmsOrderItem();
        item.setProductSkuId(skuId);
        item.setProductQuantity(quantity);
        OmsOrderDetail order = new OmsOrderDetail();
        order.setId(orderId);
        order.setOrderItemList(Collections.singletonList(item));
        return order;
    }
}
