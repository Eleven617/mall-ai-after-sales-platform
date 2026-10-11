package com.macro.mall.operations.service;

import com.macro.mall.operations.dao.HumanHandoffOperationsDao;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import java.time.*;

@Service
public class HumanHandoffOperationsService {
 @Autowired private HumanHandoffOperationsDao dao;
 public static final Set<String> REASONS=new HashSet<>(Arrays.asList("human_preference","intent_misunderstood","repeated_questions","answer_or_evidence_insufficient","tool_or_system_error","capability_or_permission_limit","business_dispute","delay_or_complex_process","unspecified"));
 private void require(boolean ok){if(!ok)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"参数不合法");}
 public Map<String,Object> list(int days,int page,int size,String topic,String source,String reason){
  require((days==7||days==30)&&page>=1&&page<=10000&&size>=1&&size<=50);
  require(topic==null||Arrays.asList("general","unknown","logistics","policy","refund","return","exchange","repair","application_follow_up").contains(topic));
  require(source==null||Arrays.asList("customer_requested","system_suggested_accepted").contains(source)); require(reason==null||REASONS.contains(reason));
  Instant end=Instant.now(); Map<String,Object> q=new HashMap<>();q.put("start",Date.from(end.minusSeconds(days*86400L)));q.put("end",Date.from(end));q.put("offset",(page-1)*size);q.put("size",size);q.put("topic",topic);q.put("source",source);q.put("reason",reason);
  // DATETIME columns are written with UTC_TIMESTAMP. Bind UTC literals so
  // the JDBC serverTimezone setting cannot shift the [start,end) window.
  java.time.format.DateTimeFormatter utc=java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneOffset.UTC);
  q.put("startSql",utc.format(end.minusSeconds(days*86400L)));q.put("endSql",utc.format(end));
  Map<String,Object> result=new HashMap<>();result.put("items",dao.page(q));result.put("totals",dao.totals(q));result.put("reasons",dao.reasons(q));result.put("page",page);result.put("size",size);result.put("windowStart",q.get("start"));result.put("windowEnd",q.get("end"));result.put("timezone","Asia/Shanghai");return result;
 }
 public Map<String,Object> detail(String ref){Map<String,Object> result=dao.detail(ref);if(result==null)throw new ResponseStatusException(HttpStatus.NOT_FOUND,"新版交接记录不存在；旧案件保留原记录");result.put("history",dao.history(ref));result.put("analysisVersions",dao.provenanceHistory(ref));result.put("context",dao.context(ref));return result;}
 public Map<String,Object> processorDetail(String ref,String username){Map<String,Object> owner=dao.caseOwner(ref);if(owner==null||(!username.equals(owner.get("assignee"))&&!(owner.get("assignee")==null&&"QUEUED".equals(owner.get("state")))))throw new ResponseStatusException(HttpStatus.FORBIDDEN,"案件不在当前处理范围");return detail(ref);}
 @Transactional public Map<String,Object> review(String ref,String reason,int version,String username){
  require(REASONS.contains(reason));Map<String,Object> owner=dao.caseOwner(ref);String actor=dao.processorRef(username);
  if(owner==null||actor==null||!actor.equals(owner.get("assignee")))throw new ResponseStatusException(HttpStatus.FORBIDDEN,"仅当前案件处理人员可复核");
  if(dao.review(ref,reason,version,actor)!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"复核版本已变化");
  dao.audit(ref,reason,version+1,actor,"human");return detail(ref);
 }
 public List<Map<String,Object>> improvements(){return dao.improvements();}
 @Transactional public Map<String,Object> createImprovement(String ref,String reason,String team,String actor){
  detail(ref);require(REASONS.contains(reason)&&Arrays.asList("engineering","policy","service").contains(team));
  Map<String,Object> q=new HashMap<>();q.put("ref",UUID.randomUUID().toString());q.put("caseRef",ref);q.put("reason",reason);q.put("team",team);q.put("actor",actor);q.put("state","OPEN");q.put("nextVersion",1);q.put("verification","not_verified");dao.createImprovement(q);dao.improvementAudit(q);return Collections.singletonMap("improvementRef",q.get("ref"));
 }
 @Transactional public void updateImprovement(String ref,String state,int version,String verification,String actor){
  Map<String,Object> current=dao.improvement(ref);if(current==null)throw new ResponseStatusException(HttpStatus.NOT_FOUND,"改进事项不存在");
  List<String> states=Arrays.asList("OPEN","TRIAGED","IN_PROGRESS","VERIFYING","CLOSED");require(states.contains(state));
  int previous=states.indexOf(String.valueOf(current.get("state"))),next=states.indexOf(state);
  require(next==previous+1 || (next==2 && previous==3));
  require(Arrays.asList("not_verified","regression_passed","manual_verified","no_change_needed").contains(verification));require(!state.equals("CLOSED")||!verification.equals("not_verified"));
  Map<String,Object> q=new HashMap<>();q.put("ref",ref);q.put("state",state);q.put("version",version);q.put("nextVersion",version+1);q.put("verification",verification);q.put("actor",actor);
  if(dao.updateImprovement(q)!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"改进版本已变化");dao.improvementAudit(q);
 }
 @Transactional public Map<String,Object> lease(){dao.expireLeases();Map<String,Object> next=dao.nextAnalysis();if(next==null)return null;String ref=String.valueOf(next.get("caseRef")),lease=UUID.randomUUID().toString();dao.lease(ref,lease);Map<String,Object> item=detail(ref);item.put("lease",lease);return item;}
 @Transactional public void finish(String ref,String lease,String state,String reason){require(Arrays.asList("SUCCEEDED","FAILED","UNAVAILABLE").contains(state));require(reason==null||REASONS.contains(reason));if(dao.finish(ref,lease,state,reason)!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"分析租约过期");if("SUCCEEDED".equals(state))dao.audit(ref,reason,1,"model-v1","model");}
 @Transactional public void finishWithProvenance(String ref,String lease,String state,String reason,String hash,String model){
  require(hash!=null&&hash.matches("[a-f0-9]{64}")&&model!=null&&model.matches("[a-zA-Z0-9_.:/-]{1,80}"));
  require(!"SUCCEEDED".equals(state)||reason!=null);finish(ref,lease,state,reason);dao.provenance(ref,lease,hash,model);
 }
 @Transactional public Map<String,Object> retention(boolean dryRun,int days){return retention(dryRun,days,365,"system");}
 @Transactional public Map<String,Object> retention(boolean dryRun,int days,int eventDays,String actor){
  require(days>=90&&days<=3650&&eventDays>=365&&eventDays<=3650);
  int count=dao.retentionCount(days),cleared=0,removed=0;
  List<String> candidates=dao.retentionCandidates(days),events=dao.expiredEvents(eventDays);
  if(!dryRun){for(String ref:candidates){cleared+=dao.clearOneProjection(ref);dao.clearContext(ref);}for(String ref:events)removed+=dao.removeEvent(ref);dao.retentionAudit(UUID.randomUUID().toString(),actor,days,eventDays,cleared,removed);}
  Map<String,Object> result=new HashMap<>();result.put("dryRun",dryRun);result.put("eligible",count);result.put("batchLimit",100);result.put("expiredEventsInBatch",events.size());result.put("projectionsCleared",cleared);result.put("eventsRemoved",removed);return result;
 }
 @Transactional public void hold(String ref,boolean held,String actor){detail(ref);dao.caseOwner(ref);dao.hold(ref,held,actor);}
}
