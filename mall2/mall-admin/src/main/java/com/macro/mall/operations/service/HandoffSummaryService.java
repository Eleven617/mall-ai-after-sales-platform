package com.macro.mall.operations.service;
import com.macro.mall.operations.dao.HandoffSummaryDao;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;

@Service
public class HandoffSummaryService {
 @Autowired private HandoffSummaryDao dao;
 private final ObjectMapper json=new ObjectMapper();
 private void require(boolean ok){if(!ok)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"invalid_summary_contract");}
 private void conflict(boolean ok){if(!ok)throw new ResponseStatusException(HttpStatus.CONFLICT,"summary_version_conflict");}
 private String encode(Object v){try{return json.writeValueAsString(v);}catch(Exception e){throw new IllegalArgumentException("invalid_summary");}}
 private Map<String,Object> decode(Object v){try{return json.readValue(String.valueOf(v),Map.class);}catch(Exception e){throw new IllegalArgumentException("invalid_summary");}}
 private String digest(Object value){try{byte[] bytes=java.security.MessageDigest.getInstance("SHA-256").digest(encode(value).getBytes(java.nio.charset.StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format("%02x",b));return out.toString();}catch(Exception e){throw new IllegalStateException("hash_unavailable");}}
 private void safeText(Object value,int limit){require(value instanceof String);String text=(String)value;require(text.length()<=limit&&!text.matches("(?is).*(bearer|password|https?://|\\d{5,}|密码|密钥|身份证|手机号|住址|姓名|@).*"));}
 private void statement(Object value,Set<String> allowed,Map<String,String> kinds,boolean step){
  if(value==null){require(!step);return;}require(value instanceof Map);Map<?,?> s=(Map<?,?>)value;
  require(s.keySet().equals(new HashSet<>(step?Arrays.asList("text","source_refs","result_kind"):Arrays.asList("text","source_refs"))));safeText(s.get("text"),240);
  require(s.get("source_refs") instanceof List);List<?> refs=(List<?>)s.get("source_refs");require(!refs.isEmpty()&&refs.size()<=8&&allowed.containsAll(refs));
  if(step){require(Arrays.asList("assistant_explanation","execution_completed","execution_failed").contains(s.get("result_kind")));String kind="assistant_explanation".equals(s.get("result_kind"))?"assistant_explanation":"execution_result";for(Object r:refs)require(kind.equals(kinds.get(r)));}
  else require(refs.stream().anyMatch(r->"customer_statement".equals(kinds.get(r))));
 }
 public Map<String,Object> detail(String ref){Map<String,Object> s=dao.get(ref);if(s==null)throw new ResponseStatusException(HttpStatus.NOT_FOUND,"summary_unavailable");s.remove("snapshot");if(s.get("summary")!=null)s.put("summary",decode(s.get("summary")));return s;}
 @Transactional public Map<String,Object> lease(){dao.exhausted();Map<String,Object> s=dao.next();if(s==null)return null;String lease=UUID.randomUUID().toString();dao.lease(String.valueOf(s.get("caseRef")),lease);s.put("lease",lease);s.put("snapshot",decode(s.get("snapshot")));return s;}
 @Transactional public void retry(String ref,int version){conflict(dao.get(ref)!=null);conflict(dao.retry(ref,version)==1);}
 private void validate(Map<String,Object> q,Map<String,Object> s){
  require(q.get("summary") instanceof Map&&q.get("projection") instanceof Map);
  Map<String,Object> summary=(Map<String,Object>)q.get("summary"),snapshot=decode(s.get("snapshot"));
  require(summary.keySet().equals(new HashSet<>(Arrays.asList("customer_goal","handling_steps","unresolved_question","customer_statements","handoff_reason_statement","uncertainty_notes","evidence_refs"))));
  Set<String> allowed=new HashSet<>();Map<String,String> kinds=new HashMap<>();for(Map<String,Object> f:(List<Map<String,Object>>)snapshot.get("fragments")){allowed.add(String.valueOf(f.get("ref")));kinds.put(String.valueOf(f.get("ref")),String.valueOf(f.get("kind")));}
  require(summary.get("evidence_refs") instanceof List&&((List<?>)summary.get("evidence_refs")).size()<=8&&allowed.containsAll((List<?>)summary.get("evidence_refs")));
  allowed.retainAll((List<?>)summary.get("evidence_refs"));
  for(String field:Arrays.asList("customer_goal","unresolved_question","handoff_reason_statement"))statement(summary.get(field),allowed,kinds,false);
  for(String field:Arrays.asList("handling_steps","customer_statements")){require(summary.get(field) instanceof List&&((List<?>)summary.get(field)).size()<=5);for(Object item:(List<?>)summary.get(field))statement(item,allowed,kinds,"handling_steps".equals(field));}
  require(summary.get("uncertainty_notes") instanceof List&&((List<?>)summary.get("uncertainty_notes")).size()<=5);for(Object note:(List<?>)summary.get("uncertainty_notes"))safeText(note,240);
  if(Boolean.TRUE.equals(snapshot.get("omitted"))||Boolean.TRUE.equals(snapshot.get("truncated")))require(!((List<?>)summary.get("uncertainty_notes")).isEmpty());
  String text=encode(summary);require(text.length()<10000);
  Map<String,Object> p=new TreeMap<>();String goal=summary.get("customer_goal")==null?"":String.valueOf(((Map<?,?>)summary.get("customer_goal")).get("text"));String question=summary.get("unresolved_question")==null?"":String.valueOf(((Map<?,?>)summary.get("unresolved_question")).get("text"));require(goal.length()<=120);
  p.put("customer_goal",goal);p.put("unresolved_question",question);p.put("customer_statement","");p.put("verified_fact_codes",Collections.emptyList());p.put("evidence_refs",summary.get("evidence_refs"));p.put("content_quality",goal.isEmpty()||question.isEmpty()?"INSUFFICIENT_CONTEXT":"READY");p.put("redaction_version","safe-lexemes-v1");p.put("summary_template_version","summary-v1");
  String hash=digest(p);p.put("projection_hash",hash);q.put("projectionHash",hash);q.put("quality",p.get("content_quality"));q.put("summary",text);q.put("projection",encode(p));
 }
 @Transactional public void finish(Map<String,Object> q){
  Map<String,Object> s=dao.get(String.valueOf(q.get("ref")));conflict(s!=null);
  require(Arrays.asList("SUCCEEDED","INSUFFICIENT_CONTEXT","FAILED").contains(q.get("state")));
  require(Arrays.asList(null,"model_contract_invalid","provider_unavailable","insufficient_context","unapproved_evidence","unsafe_summary","unsupported_business_fact","source_role_upgraded","customer_source_required","incomplete_evidence_list","unsafe_uncertainty","missing_context_limit").contains(q.get("error")));
  if("SUCCEEDED".equals(q.get("state")))validate(q,s);else q.put("summary",null);
  conflict(dao.finish(q)==1);
  if("SUCCEEDED".equals(q.get("state"))){require(Arrays.asList("READY","INSUFFICIENT_CONTEXT").contains(q.get("quality")));conflict(dao.publish(q)==1);dao.invalidate(String.valueOf(q.get("ref")));}
  dao.audit(String.valueOf(q.get("ref")),"model","summary-worker");
 }
 @Transactional public void correct(String ref,Map<String,Object> q,String actor){Map<String,Object> s=dao.get(ref);conflict(s!=null);q.put("ref",ref);validate(q,s);conflict(dao.correct(q)==1);conflict(dao.publish(q)==1);dao.invalidate(ref);dao.audit(ref,"human",actor);}
}
