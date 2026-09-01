package com.macro.mall.operations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.UmsAdmin;
import com.macro.mall.operations.domain.AiAfterSalesReviewDecisionRequest;
import com.macro.mall.operations.domain.AiAfterSalesReviewView;
import com.macro.mall.operations.service.AiAfterSalesReviewService;
import com.macro.mall.service.UmsAdminService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

import java.security.Principal;
import java.util.List;

/**
 * An authenticated operations-only review surface for new unified requests.
 * It accepts/rejects a request; it never manufactures payment, logistics,
 * warehouse, replacement, or repair fulfillment data.
 */
@Controller
@Api(tags = "AiAfterSalesReviewController")
@Tag(name = "AiAfterSalesReviewController", description = "AI 通用售后人工审核")
@RequestMapping("/ai/after-sales-review")
public class AiAfterSalesReviewController {
    @Autowired
    private UmsAdminService adminService;
    @Autowired
    private AiAfterSalesReviewService reviewService;

    @ApiOperation("读取受限的通用售后待审核/已处理列表")
    @RequestMapping(value = "/applications", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiAfterSalesReviewView>> listApplications(
            Principal principal,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "limit", defaultValue = "20") Integer limit
    ) {
        requireOperationsUsername(principal);
        try {
            return CommonResult.success(reviewService.listForReview(status, limit));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        }
    }

    @ApiOperation("人工受理或拒绝一条待审核通用售后申请")
    @RequestMapping(value = "/applications/{applicationId}/decision", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiAfterSalesReviewView> decide(
            Principal principal,
            @PathVariable("applicationId") Long applicationId,
            @RequestBody AiAfterSalesReviewDecisionRequest request
    ) {
        String reviewerUsername = requireOperationsUsername(principal);
        try {
            return CommonResult.success(reviewService.reviewPending(
                    applicationId,
                    request == null ? null : request.getAction(),
                    request == null ? null : request.getNote(),
                    reviewerUsername
            ));
        } catch (IllegalArgumentException error) {
            String message = error.getMessage();
            if ("售后申请不存在".equals(message)) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, message, error);
            }
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message, error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }

    private String requireOperationsUsername(Principal principal) {
        if (principal == null || principal.getName() == null || principal.getName().trim().isEmpty()) {
            throw new AccessDeniedException("请先以订单运营身份登录");
        }
        UmsAdmin admin = adminService.getAdminByUsername(principal.getName());
        if (admin == null || admin.getId() == null
                || !AiOperationsController.hasOperationsRole(adminService.getRoleList(admin.getId()))) {
            throw new AccessDeniedException("当前账号没有售后运营审核权限");
        }
        return admin.getUsername();
    }
}
