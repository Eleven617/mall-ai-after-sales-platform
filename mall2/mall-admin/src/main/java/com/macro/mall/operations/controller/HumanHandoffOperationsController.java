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
 @Autowired private com.macro.mall.operations.service.HandoffSemanticService semantic;
 @Autowired private com.macro.mall.operations.service.HandoffSummaryService summaries;
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
 @GetMapping("/semantic/coverage") public CommonResult<?> coverage(Principal p,@RequestParam(defaultValue="30") int days){actor(p,false);return CommonResult.success(semantic.coverage(days));}
 @GetMapping("/semantic/cases/{ref}/summary") public CommonResult<?> summary(Principal p,@PathVariable String ref){actor(p,false);return CommonResult.success(summaries.detail(ref));}
 @PostMapping("/semantic/cases/{ref}/summary") public CommonResult<?> correctSummary(Principal p,@PathVariable String ref,@RequestBody Map<String,Object> q){summaries.correct(ref,q,actor(p,false));return CommonResult.success(null);}
 @PostMapping("/semantic/cases/{ref}/summary/retry") public CommonResult<?> retrySummary(Principal p,@PathVariable String ref,@RequestParam int version){actor(p,false);summaries.retry(ref,version);return CommonResult.success(null);}
 @PostMapping("/internal/semantic/summary/lease") public CommonResult<?> summaryLease(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key){worker(key);return CommonResult.success(summaries.lease());}
 @PostMapping("/internal/semantic/summary/result") public CommonResult<?> summaryFinish(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key,@RequestBody Map<String,Object> q){worker(key);summaries.finish(q);return CommonResult.success(null);}
 @PostMapping("/semantic/rebuild") public CommonResult<?> rebuild(Principal p){actor(p,false);return CommonResult.success(semantic.rebuild());}
 @GetMapping("/semantic/cases/{ref}") public CommonResult<?> problem(Principal p,@PathVariable String ref){actor(p,false);return CommonResult.success(semantic.problem(ref));}
 @GetMapping("/semantic/cases/{ref}/candidates") public CommonResult<?> candidates(Principal p,@PathVariable String ref,@RequestParam(defaultValue="30") int days,@RequestParam(defaultValue="false") boolean crossTopic){actor(p,false);return CommonResult.success(semantic.candidates(ref,days,crossTopic));}
 @GetMapping("/semantic/groups") public CommonResult<?> groups(Principal p){actor(p,false);return CommonResult.success(semantic.groups());}
 @PostMapping("/semantic/groups") public CommonResult<?> createGroup(Principal p,@RequestBody Map<String,Object> q){return CommonResult.success(semantic.create(q,actor(p,false)));}
 @GetMapping("/semantic/groups/{ref}") public CommonResult<?> group(Principal p,@PathVariable String ref){actor(p,false);return CommonResult.success(semantic.group(ref));}
 @PostMapping("/semantic/groups/{ref}/members") public CommonResult<?> member(Principal p,@PathVariable String ref,@RequestBody Map<String,Object> q){return CommonResult.success(semantic.membership(ref,q,actor(p,false)));}
 @PostMapping("/semantic/groups/{ref}/analyses") public CommonResult<?> analyze(Principal p,@PathVariable String ref,@RequestBody Map<String,Object> q){return CommonResult.success(semantic.requestAnalysis(ref,q,actor(p,false)));}
 @PostMapping("/semantic/analyses/{ref}/review") public CommonResult<?> reviewDraft(Principal p,@PathVariable String ref){semantic.review(ref,actor(p,false));return CommonResult.success(null);}
 @PostMapping("/semantic/groups/{ref}/evidence") public CommonResult<?> evidence(Principal p,@PathVariable String ref,@RequestBody Map<String,Object> q){semantic.linkEvidence(ref,q,actor(p,false));return CommonResult.success(null);}
 @PostMapping("/internal/semantic/index/lease") public CommonResult<?> indexLease(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key){worker(key);return CommonResult.success(semantic.lease());}
 @PostMapping("/internal/semantic/index/result") public CommonResult<?> indexFinish(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key,@RequestBody Map<String,Object> q){worker(key);semantic.finish(q);return CommonResult.success(null);}
 @PostMapping("/internal/semantic/index/valid") public CommonResult<?> indexValid(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key,@RequestBody Map<String,Object> q){worker(key);return CommonResult.success(semantic.validIndex(q));}
 @PostMapping("/internal/semantic/analysis/lease") public CommonResult<?> groupLease(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key){worker(key);return CommonResult.success(semantic.analysisLease());}
 @PostMapping("/internal/semantic/analysis/result") public CommonResult<?> groupFinish(@RequestHeader(value="X-Handoff-Analysis-Key",required=false) String key,@RequestBody Map<String,Object> q){worker(key);semantic.analysisFinish(q);return CommonResult.success(null);}
}
