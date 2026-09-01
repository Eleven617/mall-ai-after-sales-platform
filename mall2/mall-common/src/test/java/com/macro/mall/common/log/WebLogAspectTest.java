package com.macro.mall.common.log;

import cn.hutool.json.JSONUtil;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;

import java.lang.reflect.Method;

import static org.assertj.core.api.Assertions.assertThat;

class WebLogAspectTest {

    private final WebLogAspect aspect = new WebLogAspect();

    @Test
    void shouldRedactRequestParametersAndOmitRequestBodies() throws Exception {
        Method method = SampleController.class.getDeclaredMethod(
                "login", String.class, LoginRequest.class
        );

        Object parameter = aspect.getParameter(
                method,
                new Object[]{"plain-text-password", new LoginRequest("plain-text-token")}
        );

        String serialized = JSONUtil.toJsonStr(parameter);
        assertThat(serialized)
                .contains("[REDACTED]", "[OMITTED_REQUEST_BODY]")
                .doesNotContain("plain-text-password", "plain-text-token");
    }

    private static class SampleController {
        void login(
                @RequestParam("password") String password,
                @RequestBody LoginRequest request
        ) {
        }
    }

    private static class LoginRequest {
        private final String token;

        private LoginRequest(String token) {
            this.token = token;
        }

        public String getToken() {
            return token;
        }
    }
}
