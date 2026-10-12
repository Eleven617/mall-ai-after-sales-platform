package com.macro.mall.portal.dao;

import java.util.Map;
import org.apache.ibatis.annotations.*;
import com.macro.mall.portal.domain.HumanHandoffRequest;

public interface HumanHandoffDao {
    @Insert("INSERT INTO ai_handoff_summary(case_ref,input_hash,snapshot_json,state,created_at,updated_at) VALUES(#{ref},#{hash},#{json},#{state},UTC_TIMESTAMP(),UTC_TIMESTAMP())")
    int summaryInput(@Param("ref") String ref,@Param("hash") String hash,@Param("json") String json,@Param("state") String state);
    @Update("UPDATE ai_handoff_problem SET index_state=IF(#{ready},'WAITING_SUMMARY','INSUFFICIENT_CONTEXT'),quality='INSUFFICIENT_CONTEXT' WHERE case_ref=#{ref}") int waitForSummary(@Param("ref") String ref,@Param("ready") boolean ready);
    @Insert("INSERT INTO ai_handoff_problem(case_ref,projection_json,projection_hash,quality,created_at,index_state,template_version) VALUES(#{ref},#{json},#{hash},#{quality},UTC_TIMESTAMP(),IF(#{quality}='READY','PENDING','INSUFFICIENT_CONTEXT'),'issue-v1')")
    int problem(@Param("ref") String ref,@Param("json") String json,@Param("hash") String hash,@Param("quality") String quality);
    @Update("UPDATE ai_handoff_record SET analysis_state='UNAVAILABLE' WHERE case_ref=#{ref}")
    int noRedundantModel(@Param("ref") String ref);
    @Insert("INSERT INTO ai_handoff_context(case_ref,plan_version,completed_steps,verified_evidence_count) VALUES(#{ref},#{r.planVersion},#{r.completedSteps},#{r.verifiedEvidenceCount})")
    int context(@Param("ref") String ref,@Param("r") HumanHandoffRequest request);
    @Insert("INSERT IGNORE INTO ai_handoff_scope(member_id,scope_key) VALUES(#{member},#{scope})")
    int ensureScope(@Param("member") Long member, @Param("scope") String scope);
    @Select("SELECT case_ref FROM ai_handoff_scope WHERE member_id=#{member} AND scope_key=#{scope} FOR UPDATE")
    String lockScope(@Param("member") Long member, @Param("scope") String scope);
    @Update("UPDATE ai_handoff_scope SET case_ref=#{caseRef} WHERE member_id=#{member} AND scope_key=#{scope}")
    int bindScope(@Param("member") Long member, @Param("scope") String scope, @Param("caseRef") String caseRef);
    @Select("SELECT r.case_ref AS caseRef,r.content_hash AS contentHash,c.state,c.state_version AS version FROM ai_handoff_request r JOIN ai_service_case c ON c.case_id=r.case_ref WHERE r.member_id=#{member} AND r.request_ref=#{request}")
    Map<String,Object> byRequest(@Param("member") Long member,@Param("request") String request);
    @Insert("INSERT INTO ai_handoff_request(member_id,request_ref,content_hash,case_ref) VALUES(#{member},#{request},#{hash},#{caseRef})")
    int bindRequest(@Param("member") Long member,@Param("request") String request,@Param("hash") String hash,@Param("caseRef") String caseRef);
    @Select("SELECT case_id AS caseRef,state,state_version AS version FROM ai_service_case WHERE member_id=#{member} AND case_id=#{caseRef} FOR UPDATE")
    Map<String,Object> caseState(@Param("member") Long member,@Param("caseRef") String caseRef);
    @Insert("INSERT INTO ai_handoff_record(case_ref,member_id,request_ref,scope_key,content_hash,trigger_source,entry_channel,business_topic,customer_reason,task_ref,stage,confirmed_at) VALUES(#{caseRef},#{member},#{r.requestRef},#{r.scopeKey},#{r.contentHash},#{r.triggerSource},#{r.entryChannel},#{r.businessTopic},#{r.customerReason},#{r.taskRef},#{r.stage},UTC_TIMESTAMP())")
    int insert(@Param("member") Long member,@Param("caseRef") String caseRef,@Param("r") HumanHandoffRequest request);
    @Insert("INSERT IGNORE INTO ai_handoff_event(event_ref,member_id,request_ref,case_ref,event_type,created_at) VALUES(#{event},#{member},#{request},#{caseRef},#{type},UTC_TIMESTAMP())")
    int event(@Param("event") String event,@Param("member") Long member,@Param("request") String request,@Param("caseRef") String caseRef,@Param("type") String type);
    @Select("SELECT e.case_ref AS caseRef,r.content_hash AS contentHash,c.state,c.state_version AS version FROM ai_handoff_event e JOIN ai_handoff_record r ON r.case_ref=e.case_ref JOIN ai_service_case c ON c.case_id=e.case_ref WHERE e.member_id=#{member} AND e.request_ref=#{request} AND e.event_type='reused' LIMIT 1")
    Map<String,Object> reused(@Param("member") Long member,@Param("request") String request);
}
