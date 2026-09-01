package com.macro.mall.operations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
import com.macro.mall.operations.domain.AiAfterSalesReviewDecisionRequest;
import com.macro.mall.operations.domain.AiAfterSalesReviewView;
import com.macro.mall.operations.service.AiAfterSalesReviewService;
import com.macro.mall.service.UmsAdminService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.access.AccessDeniedException;

import java.security.Principal;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiAfterSalesReviewControllerTest {
    @InjectMocks
    private AiAfterSalesReviewController controller;

    @Mock
    private UmsAdminService adminService;
    @Mock
    private AiAfterSalesReviewService reviewService;

    @Test
    void shouldPermitOrderOperatorToReview() {
        UmsAdmin admin = admin(9L, "order-operator");
        AiAfterSalesReviewDecisionRequest request = new AiAfterSalesReviewDecisionRequest();
        request.setAction("accept");
        request.setNote("申请已受理，后续处理进度会同步给您。");
        AiAfterSalesReviewView view = new AiAfterSalesReviewView();
        view.setApplicationId(101L);
        view.setStatus("accepted");
        when(adminService.getAdminByUsername("order-operator")).thenReturn(admin);
        when(adminService.getRoleList(9L)).thenReturn(Collections.singletonList(role("订单管理员")));
        when(reviewService.reviewPending(
                anyLong(), anyString(), anyString(), anyString()
        )).thenReturn(view);

        CommonResult<AiAfterSalesReviewView> result = controller.decide(
                principal("order-operator"), 101L, request
        );

        assertThat(result.getData().getStatus()).isEqualTo("accepted");
        ArgumentCaptor<String> reviewerCaptor = ArgumentCaptor.forClass(String.class);
        verify(reviewService).reviewPending(
                org.mockito.ArgumentMatchers.eq(101L),
                org.mockito.ArgumentMatchers.eq("accept"),
                org.mockito.ArgumentMatchers.eq("申请已受理，后续处理进度会同步给您。"),
                reviewerCaptor.capture()
        );
        assertThat(reviewerCaptor.getValue()).isEqualTo("order-operator");
    }

    @Test
    void shouldDenyNonOperationsAdministrator() {
        UmsAdmin admin = admin(10L, "product-operator");
        when(adminService.getAdminByUsername("product-operator")).thenReturn(admin);
        when(adminService.getRoleList(10L)).thenReturn(Collections.singletonList(role("商品管理员")));

        assertThatThrownBy(() -> controller.listApplications(
                principal("product-operator"), null, 20
        ))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessage("当前账号没有售后运营审核权限");
    }

    private UmsAdmin admin(Long id, String username) {
        UmsAdmin admin = new UmsAdmin();
        admin.setId(id);
        admin.setUsername(username);
        return admin;
    }

    private Principal principal(String username) {
        return () -> username;
    }

    private UmsRole role(String name) {
        UmsRole role = new UmsRole();
        role.setName(name);
        return role;
    }
}
