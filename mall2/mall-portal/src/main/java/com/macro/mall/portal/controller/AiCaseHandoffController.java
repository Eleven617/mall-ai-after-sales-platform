package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.portal.domain.AiCaseHandoffRequest;
import com.macro.mall.portal.domain.AiCaseHandoffSummary;
import com.macro.mall.portal.service.AiCaseHandoffService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * An internal capability endpoint: a valid member JWT scopes ownership, and a
 * separate service key prevents a browser from fabricating operations cases.
 */
@Controller
@Api(tags = "AiCaseHandoffController")
@Tag(name = "AiCaseHandoffController", description = "AI 客服人工转接")
@RequestMapping("/ai/cases")
public class AiCaseHandoffController {
    @Value("${ai.case-handoff.service-key}")
    private String serviceKey;

    @Autowired
    private AiCaseHandoffService caseHandoffService;

    @ApiOperation("AI 服务登记当前会员的最小人工跟进事项")
    @RequestMapping(value = "/handoffs", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiCaseHandoffSummary> createHandoff(
            @RequestHeader(value = "X-AI-Handoff-Key", required = false) String suppliedKey,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef,
            @RequestBody AiCaseHandoffRequest request
    ) {
        if (!matchesServiceKey(suppliedKey)) {
            throw new AccessDeniedException("不允许创建人工跟进事项");
        }
        if (request != null) {
            request.setCorrelationRef(correlationRef);
        }
        return CommonResult.success(caseHandoffService.createOrGetForCurrentMember(request));
    }

    private boolean matchesServiceKey(String suppliedKey) {
        if (serviceKey == null || serviceKey.trim().isEmpty() || suppliedKey == null) {
            return false;
        }
        return MessageDigest.isEqual(
                serviceKey.getBytes(StandardCharsets.UTF_8),
                suppliedKey.getBytes(StandardCharsets.UTF_8)
        );
    }
}
