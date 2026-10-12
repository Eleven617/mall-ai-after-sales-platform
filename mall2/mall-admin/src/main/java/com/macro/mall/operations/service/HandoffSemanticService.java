package com.macro.mall.operations.service;

import com.macro.mall.operations.dao.HandoffSemanticDao;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Service
public class HandoffSemanticService {
 @Autowired private HandoffSemanticDao dao;
 private final ObjectMapper json=new ObjectMapper();
 private void require(boolean ok,String code){if(!ok)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,code);}
 private void conflict(boolean ok){if(!ok)throw new ResponseStatusException(HttpStatus.CONFLICT,"semantic_version_conflict");}
 private String encode(Object value){try{return json.writeValueAsString(value);}catch(Exception e){throw new IllegalArgumentException("invalid_projection");}}
 private Object decode(Object value){try{return json.readValue(String.valueOf(value),Object.class);}catch(Exception e){throw new IllegalArgumentException("invalid_projection");}}
 private String hash(Object value){try{byte[] bytes=MessageDigest.getInstance("SHA-256").digest(encode(value).getBytes(StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format("%02x",b));return out.toString();}catch(Exception e){throw new IllegalStateException("hash_unavailable");}}
 private void ref(String ref){require(ref!=null&&ref.matches("[a-f0-9-]{36}"),"invalid_reference");}
 public Map<String,Object> problem(String ref){ref(ref);Map<String,Object> p=dao.problem(ref);if(p==null)throw new ResponseStatusException(HttpStatus.NOT_FOUND,"projection_unavailable");p.put("projection",decode(p.get("projection")));return p;}
 public Map<String,Object> candidates(String ref,int days,boolean crossTopic){
  require(days==7||days==30,"invalid_window");Map<String,Object> p=problem(ref);
  require("READY".equals(p.get("quality")),"insufficient_context");
  List<Map<String,Object>> rows=dao.candidates(days,crossTopic?null:String.valueOf(p.get("topic")));
  require(rows.size()<=5000,"narrow_search_scope");for(Map<String,Object> row:rows)row.put("projection",decode(row.get("projection")));
  Map<String,Object> result=new LinkedHashMap<>();result.put("query",p);result.put("items",rows);result.put("days",days);result.put("crossTopic",crossTopic);return result;
 }
 public Map<String,Object> coverage(int days){require(days==7||days==30,"invalid_window");return dao.coverage(days);}
 @Transactional public Map<String,Object> lease(){dao.exhausted();Map<String,Object> p=dao.next();if(p==null)return null;String lease=UUID.randomUUID().toString();dao.lease(String.valueOf(p.get("caseRef")),lease);p.put("lease",lease);p.put("projection",decode(p.get("projection")));return p;}
 @Transactional public void finish(Map<String,Object> q){require(Arrays.asList("READY","RETRYABLE","FAILED","DELETED").contains(q.get("state")),"invalid_index_state");require(String.valueOf(q.get("model")).matches("[a-zA-Z0-9_.:/-]{1,96}"),"invalid_model");conflict(dao.finish(q)==1);}
 public boolean validIndex(Map<String,Object> q){Map<String,Object> p=dao.problem(String.valueOf(q.get("ref")));return p!=null&&Objects.equals(p.get("version"),q.get("version"))&&Objects.equals(p.get("projectionHash"),q.get("hash"));}
 public List<Map<String,Object>> groups(){return dao.groups();}
 @Transactional public Map<String,Object> group(String ref){
  ref(ref);Map<String,Object> g=dao.group(ref);
  if(g==null)throw new ResponseStatusException(HttpStatus.NOT_FOUND,"group_not_found");
  List<Map<String,Object>> members=new ArrayList<>();Map<String,Integer> sources=new TreeMap<>(),reasons=new TreeMap<>();
  for(Map<String,Object> m:dao.members(ref)){
   Map<String,Object> p=dao.problem(String.valueOf(m.get("caseRef")));
   if(p!=null){p.put("projection",decode(p.get("projection")));p.put("basis",m.get("basis"));members.add(p);
    sources.merge(String.valueOf(p.get("source")),1,Integer::sum);reasons.merge(String.valueOf(p.get("customerReason")),1,Integer::sum);}
  }
  g.put("members",members);g.put("caseCount",members.size());g.put("sources",sources);g.put("customerReasons",reasons);
  g.put("history",dao.history(ref));g.put("analyses",dao.analyses(ref));return g;
 }
 @Transactional public int rebuild(){return dao.rebuild();}
 private boolean repeated(Map<String,Object> q,String actor){ref(String.valueOf(q.get("requestRef")));q.put("actor",actor);q.put("payloadHash",hash(new TreeMap<>(q)));Map<String,Object> prior=dao.request(String.valueOf(q.get("requestRef")));if(prior==null)return false;conflict(q.get("payloadHash").equals(prior.get("payloadHash"))&&actor.equals(prior.get("actor")));return true;}
 @Transactional public Map<String,Object> create(Map<String,Object> q,String actor){
  q.put("action","create");q.put("ref",q.get("requestRef"));if(repeated(q,actor))return group(String.valueOf(q.get("ref")));
  String title=String.valueOf(q.get("title"));require(title.matches("[\\p{IsHan}a-zA-Z 、，。；：（）()_-]{2,120}"),"safe_title_required");
  require(Arrays.asList("general","unknown","logistics","policy","refund","return","exchange","repair","application_follow_up").contains(q.get("topic")),"invalid_topic");dao.create(q);dao.audit(q);return group(String.valueOf(q.get("ref")));
 }
 @Transactional public Map<String,Object> membership(String ref,Map<String,Object> q,String actor){
  q.put("ref",ref);require(Arrays.asList("add","remove","reject_related","reject_unrelated").contains(q.get("action")),"invalid_group_action");
  if(repeated(q,actor))return group(ref);Map<String,Object> g=group(ref);require(q.get("version") instanceof Number,"version_required");conflict(((Number)q.get("version")).intValue()==((Number)g.get("version")).intValue());
  Map<String,Object> p=problem(String.valueOf(q.get("caseRef")));require("READY".equals(p.get("quality")),"insufficient_context");
  if("add".equals(q.get("action"))){require(Arrays.asList("same_primary_issue","same_failure_boundary").contains(q.get("basis")),"primary_issue_basis_required");q.put("projectionVersion",p.get("version"));try{dao.add(q);}catch(org.springframework.dao.DuplicateKeyException e){throw new ResponseStatusException(HttpStatus.CONFLICT,"case_already_has_primary_group");}}
  if("remove".equals(q.get("action")))conflict(dao.remove(q)==1);
  conflict(dao.advance(ref,((Number)q.get("version")).intValue())==1);dao.invalidate(ref);dao.audit(q);return group(ref);
 }
 @Transactional public Map<String,Object> requestAnalysis(String ref,Map<String,Object> q,String actor){
  q.put("ref",ref);q.put("action","analyze");q.put("analysisRef",q.get("requestRef"));if(repeated(q,actor))return Collections.singletonMap("analysisRef",q.get("analysisRef"));
  Map<String,Object> g=group(ref);conflict(Objects.equals(q.get("version"),g.get("version")));List<Map<String,Object>> members=(List<Map<String,Object>>)g.get("members");require(members.size()>=2,"two_confirmed_cases_required");
  List<Map<String,Object>> samples=new ArrayList<>();Set<String> seen=new HashSet<>();for(Map<String,Object> p:members){if("READY".equals(p.get("quality"))&&seen.add(String.valueOf(p.get("projectionHash")))&&samples.size()<5)samples.add(p);}
  if(samples.size()<2)for(Map<String,Object> p:members)if(!samples.contains(p)&&"READY".equals(p.get("quality"))&&samples.size()<2)samples.add(p);
  require(samples.size()>=2,"two_ready_cases_required");
  List<Map<String,Object>> safeSamples=new ArrayList<>();
  for(Map<String,Object> p:samples){
   Map<String,Object> safe=new LinkedHashMap<>();for(String key:Arrays.asList("caseRef","version","projectionHash","topic","source","customerReason","stage"))safe.put(key,p.get(key));
   Map<String,Object> projection=(Map<String,Object>)p.get("projection"),prose=new LinkedHashMap<>();
   for(String key:Arrays.asList("customer_goal","unresolved_question","content_quality"))prose.put(key,projection.get(key));
   safe.put("projection",prose);safeSamples.add(safe);
  }
  Map<String,Object> snapshot=new LinkedHashMap<>();snapshot.put("title",g.get("title"));snapshot.put("caseCount",members.size());snapshot.put("sampleCount",samples.size());snapshot.put("samples",safeSamples);snapshot.put("selectionVersion","diverse-hash-v1");
  q.put("snapshot",encode(snapshot));q.put("snapshotHash",hash(snapshot));dao.analysis(q);for(Map<String,Object> p:samples)dao.analysisSource(String.valueOf(q.get("analysisRef")),String.valueOf(p.get("caseRef")));dao.audit(q);return Collections.singletonMap("analysisRef",q.get("analysisRef"));
 }
 @Transactional public Map<String,Object> analysisLease(){Map<String,Object> a=dao.nextAnalysis();if(a==null)return null;String lease=UUID.randomUUID().toString();dao.analysisLease(String.valueOf(a.get("analysisRef")),lease);a.put("lease",lease);a.put("snapshot",decode(a.get("snapshot")));return a;}
 @Transactional public void analysisFinish(Map<String,Object> q){
  require(Arrays.asList("DRAFT","FAILED").contains(q.get("state")),"invalid_analysis_state");
  Map<String,Object> a=dao.analysisByRef(String.valueOf(q.get("analysisRef")));conflict(a!=null);
  require(q.get("result") instanceof Map,"invalid_draft");Map<String,Object> result=(Map<String,Object>)q.get("result");
  if("DRAFT".equals(q.get("state"))){
   require(result.keySet().equals(new HashSet<>(Arrays.asList("shared_issue","evidence_refs","hypotheses","suggested_actions","limitations"))),"invalid_draft_fields");
   Map<String,Object> snapshot=(Map<String,Object>)decode(a.get("snapshot"));Set<String> refs=new HashSet<>();
   for(Map<String,Object> p:(List<Map<String,Object>>)snapshot.get("samples"))refs.add(String.valueOf(p.get("caseRef")));
   require(result.get("evidence_refs") instanceof List&&refs.containsAll((List<?>)result.get("evidence_refs"))&&!((List<?>)result.get("evidence_refs")).isEmpty(),"unapproved_evidence");
   require(encode(result).length()<=10000,"draft_too_large");
  }else{
   require(result.keySet().equals(Collections.singleton("errorCode")),"invalid_error_fields");
   require(Arrays.asList("model_contract_invalid","unapproved_evidence","unsafe_draft","provider_unavailable").contains(result.get("errorCode")),"invalid_error_code");
  }
  q.put("result",encode(result));conflict(dao.analysisFinish(q)==1);
 }
 @Transactional public void review(String ref,String actor){Map<String,Object> a=dao.analysisByRef(ref);conflict(a!=null);Map<String,Object> g=dao.group(String.valueOf(a.get("groupRef")));conflict(g!=null&&Objects.equals(g.get("version"),a.get("groupVersion")));conflict(dao.reviewAnalysis(ref,actor)==1);}
 @Transactional public void linkEvidence(String ref,Map<String,Object> q,String actor){
  Map<String,Object> g=group(ref);conflict(Objects.equals(g.get("version"),q.get("version")));
  ref(String.valueOf(q.get("improvementRef")));q.put("ref",ref);q.put("actor",actor);
  require(dao.improvementBelongs(q)==1,"improvement_not_in_group");
  require(Arrays.asList("regression","manual_review","before_after_observation").contains(q.get("method")),"verification_method_required");
  require(String.valueOf(q.get("evidence")).matches("[a-zA-Z0-9_./:-]{3,160}"),"safe_evidence_reference_required");
  if(q.get("analysisRef")!=null){Map<String,Object> a=dao.analysisByRef(String.valueOf(q.get("analysisRef")));conflict(a!=null&&"REVIEWED".equals(a.get("state"))&&ref.equals(a.get("groupRef"))&&Objects.equals(a.get("groupVersion"),g.get("version")));}
  dao.evidence(q);
 }
}
