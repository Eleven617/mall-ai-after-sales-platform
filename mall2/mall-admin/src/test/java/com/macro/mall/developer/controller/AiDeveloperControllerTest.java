package com.macro.mall.developer.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.developer.domain.AiDeveloperActor;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
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
class AiDeveloperControllerTest {
    @InjectMocks
    private AiDeveloperController controller;
    @Mock
    private UmsAdminService adminService;

    @Test
    void shouldGrantOnlyDedicatedQualityDeveloperRole() {
        UmsAdmin admin = new UmsAdmin();
        admin.setId(11L);
        admin.setUsername("quality-developer");
        when(adminService.getAdminByUsername("quality-developer")).thenReturn(admin);
        when(adminService.getRoleList(11L)).thenReturn(Collections.singletonList(role("AI质量开发者")));

        CommonResult<AiDeveloperActor> result = controller.me(principal("quality-developer"));

        assertThat(result.getData().getUsername()).isEqualTo("quality-developer");
        assertThat(result.getData().getCapabilities()).containsExactly("quality_evaluation");
    }

    @Test
    void shouldRejectOperationsRoleEvenWithValidAdminToken() {
        UmsAdmin admin = new UmsAdmin();
        admin.setId(7L);
        admin.setUsername("order-operator");
        when(adminService.getAdminByUsername("order-operator")).thenReturn(admin);
        when(adminService.getRoleList(7L)).thenReturn(Collections.singletonList(role("订单管理员")));

        assertThatThrownBy(() -> controller.me(principal("order-operator")))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessage("当前账号没有 AI 质量评测权限");
    }

    @Test
    void shouldNotTreatSuperOrProductAdministratorAsDeveloper() {
        assertThat(AiDeveloperController.hasQualityDeveloperRole(Arrays.asList(role("超级管理员")))).isFalse();
        assertThat(AiDeveloperController.hasQualityDeveloperRole(Arrays.asList(role("商品管理员")))).isFalse();
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
