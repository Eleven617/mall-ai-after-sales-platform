package com.macro.mall.serviceoperations.controller;

import com.macro.mall.model.UmsRole;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;

class AiServiceOperationsControllerTest {
    @Test
    void shouldAllowOnlyDedicatedProcessorRole() {
        UmsRole processor = new UmsRole();
        processor.setName("售后处理人员");
        UmsRole operations = new UmsRole();
        operations.setName("订单管理员");

        assertThat(AiServiceOperationsController.hasProcessorRole(Collections.singletonList(processor))).isTrue();
        assertThat(AiServiceOperationsController.hasProcessorRole(Collections.singletonList(operations))).isFalse();
        assertThat(AiServiceOperationsController.hasProcessorRole(Arrays.asList(operations, processor))).isTrue();
    }
}
