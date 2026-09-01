package com.macro.mall.developer.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.developer.domain.AiDeveloperActor;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
import com.macro.mall.service.UmsAdminService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import java.security.Principal;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Authentication boundary for the developer-only, synthetic quality runner.
 * It exposes no business data.  FastAPI verifies this endpoint before it
 * serves a local quality run, so customer, product and operations identities
 * cannot reuse their tokens on the developer surface.
 */
@Controller
@Api(tags = "AiDeveloperController")
@Tag(name = "AiDeveloperController", description = "AI 质量评测开发者身份")
@RequestMapping("/ai/developer")
public class AiDeveloperController {
    private static final String QUALITY_DEVELOPER_ROLE = "AI质量开发者";

    @Autowired
    private UmsAdminService adminService;

    @ApiOperation("验证当前 AI 质量开发者身份")
    @RequestMapping(value = "/me", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiDeveloperActor> me(Principal principal) {
        return CommonResult.success(requireQualityDeveloper(principal));
    }

    private AiDeveloperActor requireQualityDeveloper(Principal principal) {
        if (principal == null || principal.getName() == null || principal.getName().trim().isEmpty()) {
            throw new AccessDeniedException("请先以 AI 质量开发者身份登录");
        }
        UmsAdmin admin = adminService.getAdminByUsername(principal.getName());
        if (admin == null || admin.getId() == null || !hasQualityDeveloperRole(adminService.getRoleList(admin.getId()))) {
            throw new AccessDeniedException("当前账号没有 AI 质量评测权限");
        }
        AiDeveloperActor actor = new AiDeveloperActor();
        actor.setUsername(admin.getUsername());
        actor.setCapabilities(Collections.singletonList("quality_evaluation"));
        return actor;
    }

    static boolean hasQualityDeveloperRole(List<UmsRole> roles) {
        if (roles == null) {
            return false;
        }
        return roles.stream().anyMatch(role -> role != null && QUALITY_DEVELOPER_ROLE.equals(role.getName()));
    }
}
