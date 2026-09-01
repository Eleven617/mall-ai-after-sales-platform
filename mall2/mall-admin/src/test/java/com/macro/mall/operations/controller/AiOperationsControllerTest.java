package com.macro.mall.operations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
import com.macro.mall.operations.domain.AiOperationsActor;
import com.macro.mall.operations.service.AiOperationsService;
import com.macro.mall.service.UmsAdminService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.access.AccessDeniedException;

import java.security.Principal;
import java.util.Arrays;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiOperationsControllerTest {
    @InjectMocks
    private AiOperationsController controller;
    @Mock
    private UmsAdminService adminService;
    @Mock
    private AiOperationsService operationsService;

    @Test
    void shouldGrantOnlyOrderOperationsRole() {
        UmsAdmin admin = new UmsAdmin();
        admin.setId(9L);
        admin.setUsername("order-operator");
        when(adminService.getAdminByUsername("order-operator")).thenReturn(admin);
        when(adminService.getRoleList(9L)).thenReturn(Collections.singletonList(role("订单管理员")));

        CommonResult<AiOperationsActor> result = controller.me(principal("order-operator"));

        assertThat(result.getData().getUsername()).isEqualTo("order-operator");
        assertThat(result.getData().getCapabilities()).contains("operations_analysis", "case_review");
    }

    @Test
    void shouldRejectProductAdministratorEvenWithValidAdminToken() {
        UmsAdmin admin = new UmsAdmin();
        admin.setId(10L);
        admin.setUsername("product-operator");
        when(adminService.getAdminByUsername("product-operator")).thenReturn(admin);
        when(adminService.getRoleList(10L)).thenReturn(Collections.singletonList(role("商品管理员")));

        assertThatThrownBy(() -> controller.me(principal("product-operator")))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessage("当前账号没有售后运营分析权限");
    }

    @Test
    void shouldRecognizeOnlyExplicitAllowedRoles() {
        assertThat(AiOperationsController.hasOperationsRole(Arrays.asList(role("超级管理员")))).isTrue();
        assertThat(AiOperationsController.hasOperationsRole(Arrays.asList(role("商品管理员")))).isFalse();
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
