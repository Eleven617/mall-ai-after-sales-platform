package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.portal.domain.HumanHandoffRequest;
import com.macro.mall.portal.service.impl.HumanHandoffService;
import org.springframework.beans.factory.annotation.*;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@RestController
@RequestMapping("/ai/human-handoffs")
public class HumanHandoffController {
    @Autowired private HumanHandoffService service;
    @Value("${ai.case-handoff.service-key}") private String key;
    private void authenticate(String supplied) {
        if(key==null || key.isEmpty() || supplied==null || !MessageDigest.isEqual(key.getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8))) throw new AccessDeniedException("交接服务身份无效");
    }
    @PostMapping
    public CommonResult<Map<String,Object>> create(@RequestHeader(value="X-AI-Handoff-Key",required=false) String supplied,@RequestBody HumanHandoffRequest request) {
        authenticate(supplied); return CommonResult.success(service.create(request));
    }
    @GetMapping("/by-request/{request}")
    public CommonResult<Map<String,Object>> find(@RequestHeader(value="X-AI-Handoff-Key",required=false) String supplied,@PathVariable String request) {
        authenticate(supplied); return CommonResult.success(service.find(request));
    }
    @PostMapping("/events/{request}/{type}")
    public CommonResult<?> event(@RequestHeader(value="X-AI-Handoff-Key",required=false) String supplied,@PathVariable String request,@PathVariable String type) {
        authenticate(supplied);service.event(request,type);return CommonResult.success(null);
    }
}
