package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.portal.domain.AiAfterSalesApplicationSummary;
import com.macro.mall.portal.domain.AiAfterSalesActionRequest;
import com.macro.mall.portal.domain.AiAfterSalesActionStatus;
import com.macro.mall.portal.domain.AiAfterSalesApplyRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilityRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilitySummary;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesSubmissionStatus;
import com.macro.mall.portal.service.AiAfterSalesApplicationService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

/**
 * AI-facing, token-scoped facade for the unified after-sales core. It is not a
 * browser write API: FastAPI owns the confirmation state and forwards the JWT.
 * Customer reads remain JWT-scoped, while each business write additionally
 * requires FastAPI's internal capability key.
 */
@Controller
@Api(tags = "AiAfterSalesApplicationController")
@Tag(name = "AiAfterSalesApplicationController", description = "AI 通用售后申请")
@RequestMapping("/after-sales/ai")
public class AiAfterSalesApplicationController {
    @Value("${ai.after-sales.service-key}")
    private String serviceKey;

    @Autowired
    private AiAfterSalesApplicationService applicationService;

    @ApiOperation("按当前用户真实订单状态核验售后申请资格")
    @RequestMapping(value = "/eligibility", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiAfterSalesEligibilitySummary> checkEligibility(
            @RequestBody AiAfterSalesEligibilityRequest request
    ) {
        return CommonResult.success(applicationService.checkEligibility(request));
    }

    @ApiOperation("AI 服务在客户明确确认后创建统一售后申请")
    @RequestMapping(value = "/applications", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiAfterSalesApplicationSummary> create(
            @RequestHeader(value = "X-AI-After-Sales-Key", required = false) String suppliedKey,
            @RequestBody AiAfterSalesApplyRequest request
    ) {
        requireServiceKey(suppliedKey);
        return CommonResult.success(applicationService.createForAi(request));
    }

    @ApiOperation("查询当前用户一次售后提交的最终结果")
    @RequestMapping(value = "/submissions/{idempotencyKey}", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiAfterSalesSubmissionStatus> getSubmissionStatus(
            @PathVariable("idempotencyKey") String idempotencyKey
    ) {
        return CommonResult.success(applicationService.getSubmissionStatus(idempotencyKey));
    }

    @ApiOperation("查询当前登录用户的通用售后申请记录")
    @RequestMapping(value = "/applications", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiAfterSalesApplicationSummary>> listMine() {
        return CommonResult.success(applicationService.listForAiCurrentMember());
    }

    @ApiOperation("取消当前用户仍待审核的售后申请")
    @RequestMapping(value = "/applications/{applicationId}/cancel", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiAfterSalesApplicationSummary> cancel(
            @PathVariable("applicationId") Long applicationId,
            @RequestHeader(value = "X-AI-After-Sales-Key", required = false) String suppliedKey,
            @RequestBody AiAfterSalesActionRequest request
    ) {
        requireServiceKey(suppliedKey);
        return CommonResult.success(applicationService.cancelForAiCurrentMember(applicationId, request));
    }

    @ApiOperation("修改当前用户仍待审核申请的原因和说明")
    @RequestMapping(value = "/applications/{applicationId}", method = RequestMethod.PUT)
    @ResponseBody
    public CommonResult<AiAfterSalesApplicationSummary> modify(
            @PathVariable("applicationId") Long applicationId,
            @RequestHeader(value = "X-AI-After-Sales-Key", required = false) String suppliedKey,
            @RequestBody AiAfterSalesActionRequest request
    ) {
        requireServiceKey(suppliedKey);
        return CommonResult.success(applicationService.modifyForAiCurrentMember(applicationId, request));
    }

    @ApiOperation("查询当前用户一次已确认售后操作的最终结果")
    @RequestMapping(value = "/actions/{actionId}", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiAfterSalesActionStatus> getActionStatus(
            @PathVariable("actionId") String actionId
    ) {
        return CommonResult.success(applicationService.getActionStatus(actionId));
    }

    @ApiOperation("受服务端能力密钥保护的履约适配器回调")
    @RequestMapping(value = "/fulfillment/callback", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiAfterSalesApplicationSummary> fulfillmentCallback(
            @RequestHeader(value = "X-AI-After-Sales-Key", required = false) String suppliedKey,
            @RequestBody AiAfterSalesFulfillmentCallbackRequest request
    ) {
        requireServiceKey(suppliedKey);
        return CommonResult.success(applicationService.recordFulfillmentCallback(request));
    }

    private void requireServiceKey(String suppliedKey) {
        if (serviceKey == null || serviceKey.trim().isEmpty() || suppliedKey == null
                || !MessageDigest.isEqual(
                serviceKey.getBytes(StandardCharsets.UTF_8),
                suppliedKey.getBytes(StandardCharsets.UTF_8)
        )) {
            throw new AccessDeniedException("不允许直接提交或修改售后申请");
        }
    }
}
