package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.portal.domain.AiCustomerConversationDetail;
import com.macro.mall.portal.domain.AiCustomerConversationSummary;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptRequest;
import com.macro.mall.portal.service.AiCustomerConversationService;
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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

/**
 * Customer history endpoints are protected by the current member JWT. Only the
 * paired transcript writer additionally requires FastAPI's internal key.
 */
@Controller
@Api(tags = "AiCustomerConversationController")
@Tag(name = "AiCustomerConversationController", description = "AI 客服历史会话")
@RequestMapping("/ai/conversations")
public class AiCustomerConversationController {
    @Value("${ai.case-handoff.service-key}")
    private String serviceKey;

    @Autowired
    private AiCustomerConversationService conversationService;

    @ApiOperation("创建当前会员的空白客服会话")
    @RequestMapping(method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<AiCustomerConversationSummary> create(
            @RequestParam("conversationId") String conversationId
    ) {
        return CommonResult.success(conversationService.createForCurrentMember(conversationId));
    }

    @ApiOperation("读取当前会员的历史会话列表")
    @RequestMapping(method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<List<AiCustomerConversationSummary>> list() {
        return CommonResult.success(conversationService.listForCurrentMember());
    }

    @ApiOperation("读取当前会员的一段历史会话")
    @RequestMapping(value = "/{conversationId}", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<AiCustomerConversationDetail> get(@PathVariable String conversationId) {
        return CommonResult.success(conversationService.getForCurrentMember(conversationId));
    }

    @ApiOperation("删除当前会员的一段历史会话")
    @RequestMapping(value = "/{conversationId}", method = RequestMethod.DELETE)
    @ResponseBody
    public CommonResult delete(@PathVariable String conversationId) {
        conversationService.deleteForCurrentMember(conversationId);
        return CommonResult.success(null);
    }

    @ApiOperation("AI 服务写入当前会员的一次客户可见对话")
    @RequestMapping(value = "/{conversationId}/transcript", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult appendTranscript(
            @PathVariable String conversationId,
            @RequestHeader(value = "X-AI-Handoff-Key", required = false) String suppliedKey,
            @RequestBody AiCustomerConversationTranscriptRequest request
    ) {
        if (!matchesServiceKey(suppliedKey)) {
            throw new AccessDeniedException("不允许写入历史会话");
        }
        conversationService.appendTranscriptForCurrentMember(conversationId, request);
        return CommonResult.success(null);
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
