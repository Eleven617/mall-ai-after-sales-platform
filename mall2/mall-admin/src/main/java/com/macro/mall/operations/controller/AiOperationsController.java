package com.macro.mall.operations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
import com.macro.mall.operations.domain.AiOperationsActor;
import com.macro.mall.operations.domain.AiOperationsCaseView;
import com.macro.mall.operations.domain.AiOperationsMetrics;
import com.macro.mall.operations.service.AiOperationsService;
import com.macro.mall.service.UmsAdminService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

import java.security.Principal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * A narrow, read-only internal surface. Path-level Spring authentication is
 * necessary but not sufficient: every handler also enforces the true role
 * boundary because the legacy dynamic resource table may not know new paths.
 */
@Controller
@Api(tags = "AiOperationsController")
@Tag(name = "AiOperationsController", description = "AI 售后运营只读分析")
@RequestMapping("/ai/operations")
public class AiOperationsController {
    private static final Set<String> ALLOWED_ROLE_NAMES = new HashSet<>(
            Arrays.asList("订单管理员", "超级管理员")
    );

    @Autowired
    private UmsAdminService adminService;
    @Autowired
    private AiOperationsService operationsService;

    @ApiOperation("验证当前运营人员的分析权限")
    @RequestMapping(value = "/me", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiOperationsActor> me(Principal principal) {
        return CommonResult.success(requireOperationsActor(principal));
    }

    @ApiOperation("读取最小化人工跟进事项列表")
    @RequestMapping(value = "/cases", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiOperationsCaseView>> listCases(
            Principal principal,
            @RequestParam(value = "limit", defaultValue = "20") Integer limit
    ) {
        requireOperationsActor(principal);
        return CommonResult.success(operationsService.listRecentCases(limit));
    }

    @ApiOperation("读取一个最小化人工跟进事项")
    @RequestMapping(value = "/cases/{caseId}", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiOperationsCaseView> getCase(
            Principal principal,
            @PathVariable("caseId") String caseId
    ) {
        requireOperationsActor(principal);
        if (caseId == null || !caseId.matches("[a-f0-9-]{36}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "事项标识不合法");
        }
        AiOperationsCaseView value = operationsService.getCase(caseId);
        if (value == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "事项不存在");
        }
        return CommonResult.success(value);
    }

    @ApiOperation("读取非个人化售后运营聚合")
    @RequestMapping(value = "/after-sales-metrics", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiOperationsMetrics> getMetrics(
            Principal principal,
            @RequestParam(value = "windowDays", defaultValue = "7") Integer windowDays
    ) {
        requireOperationsActor(principal);
        if (windowDays == null || (windowDays != 7 && windowDays != 30)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "仅支持 7 或 30 天窗口");
        }
        return CommonResult.success(operationsService.getMetrics(windowDays));
    }

    private AiOperationsActor requireOperationsActor(Principal principal) {
        if (principal == null || principal.getName() == null || principal.getName().trim().isEmpty()) {
            throw new AccessDeniedException("请先以订单运营身份登录");
        }
        UmsAdmin admin = adminService.getAdminByUsername(principal.getName());
        if (admin == null || admin.getId() == null || !hasOperationsRole(adminService.getRoleList(admin.getId()))) {
            throw new AccessDeniedException("当前账号没有售后运营分析权限");
        }
        AiOperationsActor actor = new AiOperationsActor();
        actor.setUsername(admin.getUsername());
        actor.setCapabilities(new ArrayList<>(Arrays.asList("operations_analysis", "case_review")));
        return actor;
    }

    static boolean hasOperationsRole(List<UmsRole> roles) {
        if (roles == null) {
            return false;
        }
        for (UmsRole role : roles) {
            if (role != null && ALLOWED_ROLE_NAMES.contains(role.getName())) {
                return true;
            }
        }
        return false;
    }
}
