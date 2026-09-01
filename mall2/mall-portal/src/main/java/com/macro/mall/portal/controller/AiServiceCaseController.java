package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.portal.domain.AiServiceCaseCancelRequest;
import com.macro.mall.portal.domain.AiServiceCaseCustomerInformationRequest;
import com.macro.mall.portal.domain.AiServiceCasePublicView;
import com.macro.mall.portal.domain.AiServiceCaseReopenRequest;
import com.macro.mall.portal.domain.AiServiceCaseTimelineEntry;
import com.macro.mall.portal.service.AiServiceCaseService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

/** Current-member service-case progress and bounded supplemental information. */
@Controller
@Api(tags = "AiServiceCaseController")
@Tag(name = "AiServiceCaseController", description = "AI 售后人工协同客户进度")
@RequestMapping("/service-cases")
public class AiServiceCaseController {
    @Autowired
    private AiServiceCaseService serviceCaseService;

    @ApiOperation("读取当前会员自己的人工协同案件")
    @RequestMapping(value = "/mine", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiServiceCasePublicView>> mine() {
        return CommonResult.success(serviceCaseService.listMine());
    }

    @ApiOperation("读取当前会员自己的客户可见案件时间线")
    @RequestMapping(value = "/{caseId}/timeline", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiServiceCaseTimelineEntry>> timeline(@PathVariable("caseId") String caseId) {
        try {
            return CommonResult.success(serviceCaseService.timelineMine(caseId));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "案件不存在或不属于当前用户", error);
        }
    }

    @ApiOperation("在明确要求补件时提交允许范围内的信息")
    @RequestMapping(value = "/{caseId}/customer-information", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiServiceCasePublicView> customerInformation(
            @PathVariable("caseId") String caseId,
            @RequestBody AiServiceCaseCustomerInformationRequest request,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef
    ) {
        try {
            return CommonResult.success(serviceCaseService.submitCustomerInformation(caseId, request, correlationRef));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }

    @ApiOperation("取消当前会员仍可取消的人工协同事项")
    @RequestMapping(value = "/{caseId}/cancel", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiServiceCasePublicView> cancel(
            @PathVariable("caseId") String caseId,
            @RequestBody AiServiceCaseCancelRequest request,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef
    ) {
        try {
            return CommonResult.success(serviceCaseService.cancelMine(caseId, request, correlationRef));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }

    @ApiOperation("在限定处理窗口内重新开启本人已处理完的人工协同事项")
    @RequestMapping(value = "/{caseId}/reopen", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiServiceCasePublicView> reopen(
            @PathVariable("caseId") String caseId,
            @RequestBody AiServiceCaseReopenRequest request,
            @RequestHeader(value = "X-Correlation-Id", required = false) String correlationRef
    ) {
        try {
            return CommonResult.success(serviceCaseService.reopenMine(caseId, request, correlationRef));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
    }
}
