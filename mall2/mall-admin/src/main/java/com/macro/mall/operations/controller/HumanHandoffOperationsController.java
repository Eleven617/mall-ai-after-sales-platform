package com.macro.mall.operations.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.model.*;
import com.macro.mall.service.UmsAdminService;
import com.macro.mall.operations.service.HumanHandoffOperationsService;
import org.springframework.beans.factory.annotation.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.AccessDeniedException;
import java.security.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

@RestController
@RequestMapping("/ai/handoff-management")
public class HumanHandoffOperationsController {
 @Autowired private HumanHandoffOperationsService service;
 @Autowired private UmsAdminService admins;
 @Value("${ai.handoff-analysis.service-key:}") private String analysisKey;
 @Value("${AI_CASE_HANDOFF_SERVICE_KEY:}") private String baseServiceKey;
 private String actor(Principal principal,boolean processor){
  if(principal==null)throw new AccessDeniedException("请登录");
  UmsAdmin admin=admins.getAdminByUsername(principal.getName());if(admin==null)throw new AccessDeniedException("身份无效");
  List<UmsRole> roles=admins.getRoleList(admin.getId());
  boolean allowed=roles!=null&&roles.stream().anyMatch(r->processor?"售后处理人员".equals(r.getName()):Arrays.asList("订单管理员","超级管理员").contains(r.getName()));
  if(!allowed)throw new AccessDeniedException("角色不具备此权限");return admin.getUsername();
 }
 public static class Review {public String reason;public int version;}
 public static class Improvement {public String caseRef;public String reason;public String team;public String state;public int version;public String verificationCode;}
 public static class Analysis {public String caseRef;public String lease;public String state;public String reason;public String inputHash;public String modelVersion;}
 @GetMapping public CommonResult<?> page(Principal p,@RequestParam(defaultValue="7") int days,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size,@RequestParam(required=false) String topic,@RequestParam(required=false) String source,@RequestParam(required=false) String reason){actor(p,false);return CommonResult.success(service.list(days,page,size,topic,source,reason));}
 @GetMapping("/cases/{ref}") public CommonResult<?> detail(Principal p,@PathVariable String ref){actor(p,false);return CommonResult.success(service.detail(ref));}
 @GetMapping("/processor/cases/{ref}") public CommonResult<?> processorDetail(Principal p,@PathVariable String ref){String username=actor(p,true);return CommonResult.success(service.processorDetail(ref,username));}
 @PostMapping("/processor/cases/{ref}/review") public CommonResult<?> review(Principal p,@PathVariable String ref,@RequestBody Review r){return CommonResult.success(service.review(ref,r.reason,r.version,actor(p,true)));}
 @GetMapping("/improvements") public CommonResult<?> improvements(Principal p){actor(p,false);return CommonResult.success(service.improvements());}
 @PostMapping("/improvements") public CommonResult<?> create(Principal p,@RequestBody Improvement r){return CommonResult.success(service.createImprovement(r.caseRef,r.reason,r.team,actor(p,false)));}
 @PatchMapping("/improvements/{ref}") public CommonResult<?> update(Principal p,@PathVariable String ref,@RequestBody Improvement r){service.updateImprovement(ref,r.state,r.version,r.verificationCode,actor(p,false));return CommonResult.success(null);}
 @PostMapping("/retention") public CommonResult<?> retention(Principal p,@RequestParam(defaultValue="true") boolean dryRun,@RequestParam(defaultValue="90") int days,@RequestParam(defaultValue="365") int eventDays){return CommonResult.success(service.retention(dryRun,days,eventDays,actor(p,false)));}
 @PostMapping("/cases/{ref}/retention-hold") public CommonResult<?> hold(Principal p,@PathVariable String ref,@RequestParam boolean held){service.hold(ref,held,actor(p,false));return CommonResult.success(null);}
 private void worker(String key){
  String expected=analysisKey;
  if(expected.isEmpty()&&!baseServiceKey.isEmpty())try{byte[] digest=MessageDigest.getInstance("SHA-256").digest((baseServiceKey+":handoff-analysis-v1").getBytes(StandardCharsets.UTF_8));StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format("%02x",b));expected=hex.toString();}catch(NoSuchAlgorithmException e){throw new IllegalStateException("分析身份不可用");}
  if(expected.isEmpty()||key==null||!MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),key.getBytes(StandardCharsets.UTF_8)))throw new AccessDeniedException("分析服务身份无效");
 }
 @PostMapping("/internal/lease") public CommonResult<?> lease(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key){worker(key);return CommonResult.success(service.lease());}
 @PostMapping("/internal/result") public CommonResult<?> finish(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key,@RequestBody Analysis r){worker(key);service.finishWithProvenance(r.caseRef,r.lease,r.state,r.reason,r.inputHash,r.modelVersion);return CommonResult.success(null);}
}
