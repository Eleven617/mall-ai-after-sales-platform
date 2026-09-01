package com.macro.mall.config;

import org.junit.jupiter.api.Test;
import org.mybatis.spring.annotation.MapperScan;

import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;

class MyBatisConfigTest {
    @Test
    void shouldScanTheReadOnlyOperationsDaoPackage() {
        MapperScan mapperScan = MyBatisConfig.class.getAnnotation(MapperScan.class);

        assertThat(mapperScan).isNotNull();
        assertThat(Arrays.asList(mapperScan.value()))
                .contains("com.macro.mall.operations.dao");
    }
}
