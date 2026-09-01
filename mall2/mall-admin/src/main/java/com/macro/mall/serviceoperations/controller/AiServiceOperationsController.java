package com.macro.mall.serviceoperations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.model.UmsRole;
import com.macro.mall.service.UmsAdminService;
import com.macro.mall.serviceoperations.domain.AiServiceCaseActionRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseClaimRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorView;
import com.macro.mall.serviceoperations.domain.AiServiceProcessorActor;
import com.macro.mall.serviceoperations.service.AiServiceOperationsService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

import java.security.Principal;
import java.util.Collections;
import java.util.List;

/** Separate, least-privileged human service-case workbench authority. */
@Controller
@Api(tags = "AiServiceOperationsController")
@Tag(name = "AiServiceOperationsController", description = "AI 售后人工协同处理")
@RequestMapping("/ai/service-operations")
public class AiServiceOperationsController {
    private static final String PROCESSOR_ROLE = "售后处理人员";

    @Autowired
    private UmsAdminService adminService;
    @Autowired
    private AiServiceOperationsService serviceOperationsService;

    @ApiOperation("验证当前人工售后处理人员身份")
    @RequestMapping(value = "/me", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiServiceProcessorActor> me(Principal principal) {
        String username = requireProcessorUsername(principal);
        AiServiceProcessorActor actor = new AiServiceProcessorActor();
        actor.setUsername(username);
        actor.setCapabilities(Collections.singletonList("service_case_handling"));
        return CommonResult.success(actor);
    }

    @ApiOperation("读取可领取或本人已领取的最小人工协同案件")
    @RequestMapping(value = "/cases", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiServiceCaseProcessorView>> cases(
            Principal principal,
            @RequestParam(value = "limit", defaultValue = "20") Integer limit
    ) {
        try {
            return CommonResult.success(serviceOperationsService.listVisible(requireProcessorUsername(principal), limit));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        }
    }

    @ApiOperation("领取一个本人有权限的排队人工协同案件")
    @RequestMapping(value = "/cases/{caseId}/claim", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiServiceCaseProcessorView> claim(
            Principal principal,
            @PathVariable("caseId") String caseId,
            @RequestBody AiServiceCaseClaimRequest request,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef
    ) {
        try {
            return CommonResult.success(serviceOperationsService.claim(
                    caseId, request, requireProcessorUsername(principal), correlationRef
            ));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }

    @ApiOperation("请求补件、开始核验、处理或结案一个本人已领取的案件")
    @RequestMapping(value = "/cases/{caseId}/actions", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiServiceCaseProcessorView> action(
            Principal principal,
            @PathVariable("caseId") String caseId,
            @RequestBody AiServiceCaseActionRequest request,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef
    ) {
        try {
            return CommonResult.success(serviceOperationsService.act(
                    caseId, request, requireProcessorUsername(principal), correlationRef
            ));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }

    private String requireProcessorUsername(Principal principal) {
        if (principal == null || principal.getName() == null || principal.getName().trim().isEmpty()) {
            throw new AccessDeniedException("请先以售后处理人员身份登录");
        }
        UmsAdmin admin = adminService.getAdminByUsername(principal.getName());
        if (admin == null || admin.getId() == null || !hasProcessorRole(adminService.getRoleList(admin.getId()))) {
            throw new AccessDeniedException("当前账号没有人工售后处理权限");
        }
        return admin.getUsername();
    }

    static boolean hasProcessorRole(List<UmsRole> roles) {
        if (roles == null) {
            return false;
        }
        for (UmsRole role : roles) {
            if (role != null && PROCESSOR_ROLE.equals(role.getName())) {
                return true;
            }
        }
        return false;
    }
}
