package com.macro.mall.operations.dao;

import java.util.*;
import org.apache.ibatis.annotations.*;

public interface HumanHandoffOperationsDao {
    @Select("SELECT plan_version AS planVersion,completed_steps AS completedSteps,verified_evidence_count AS verifiedEvidenceCount FROM ai_handoff_context WHERE case_ref=#{ref}")
    Map<String,Object> context(@Param("ref") String ref);
    @Delete("DELETE FROM ai_handoff_context WHERE case_ref=#{ref}")
    int clearContext(@Param("ref") String ref);
    String FIELDS="r.case_ref AS caseRef,r.trigger_source AS source,r.entry_channel AS channel,r.business_topic AS topic,r.customer_reason AS customerReason,r.stage,r.confirmed_at AS confirmedAt,r.verified_reason AS verifiedReason,r.review_version AS reviewVersion,r.model_reason AS modelReason,r.analysis_state AS analysisState,r.projection_cleared AS projectionCleared,c.state,c.state_version AS caseVersion";
    String FILTER=" FROM ai_handoff_record r JOIN ai_service_case c ON c.case_id=r.case_ref WHERE r.confirmed_at &gt;= #{startSql} AND r.confirmed_at &lt; #{endSql} <if test='topic != null'> AND r.business_topic=#{topic}</if><if test='source != null'> AND r.trigger_source=#{source}</if><if test='reason != null'> AND COALESCE(r.verified_reason,r.model_reason,r.customer_reason)=#{reason}</if>";
    @Select("<script>SELECT "+FIELDS+FILTER+" ORDER BY r.confirmed_at DESC,r.case_ref LIMIT #{size} OFFSET #{offset}</script>")
    List<Map<String,Object>> page(Map<String,Object> query);
    @Select("<script>SELECT COUNT(*) AS total,SUM(r.trigger_source='customer_requested') AS customerRequested,SUM(r.trigger_source='system_suggested_accepted') AS suggestedAccepted,SUM(c.state NOT IN ('CLOSED','CANCELLED','RESOLVED')) AS pendingInWindow"+FILTER+"</script>")
    Map<String,Object> totals(Map<String,Object> query);
    @Select("<script>SELECT COALESCE(r.verified_reason,r.model_reason,r.customer_reason) AS reason,COUNT(*) AS count"+FILTER+" GROUP BY COALESCE(r.verified_reason,r.model_reason,r.customer_reason)</script>")
    List<Map<String,Object>> reasons(Map<String,Object> query);
    @Select("SELECT "+FIELDS+" FROM ai_handoff_record r JOIN ai_service_case c ON c.case_id=r.case_ref WHERE r.case_ref=#{ref}")
    Map<String,Object> detail(@Param("ref") String ref);
    @Select("SELECT state,state_version AS version,assignee_ref AS assignee FROM ai_service_case WHERE case_id=#{ref} FOR UPDATE")
    Map<String,Object> caseOwner(@Param("ref") String ref);
    @Select("SELECT username FROM ums_admin WHERE username=#{username} AND status=1")
    String processorRef(@Param("username") String username);
    @Update("UPDATE ai_handoff_record SET verified_reason=#{reason},review_version=review_version+1,reviewer_ref=#{actor},reviewed_at=UTC_TIMESTAMP() WHERE case_ref=#{ref} AND review_version=#{version}")
    int review(@Param("ref") String ref,@Param("reason") String reason,@Param("version") int version,@Param("actor") String actor);
    @Insert("INSERT INTO ai_handoff_analysis(case_ref,revision,actor_ref,source,reason,created_at) VALUES(#{ref},#{version},#{actor},#{source},#{reason},UTC_TIMESTAMP())")
    int audit(@Param("ref") String ref,@Param("reason") String reason,@Param("version") int version,@Param("actor") String actor,@Param("source") String source);
    @Select("SELECT revision,source,reason,created_at AS createdAt FROM ai_handoff_analysis WHERE case_ref=#{ref} ORDER BY created_at,revision")
    List<Map<String,Object>> history(@Param("ref") String ref);
    @Insert("INSERT INTO ai_operations_improvement(improvement_ref,case_ref,reason,team,state,version,verification_code,actor_ref,created_at,updated_at) VALUES(#{ref},#{caseRef},#{reason},#{team},'OPEN',1,'not_verified',#{actor},UTC_TIMESTAMP(),UTC_TIMESTAMP())")
    int createImprovement(Map<String,Object> request);
    @Select("SELECT improvement_ref AS improvementRef,case_ref AS caseRef,reason,team,state,version,verification_code AS verificationCode,updated_at AS updatedAt FROM ai_operations_improvement ORDER BY updated_at DESC LIMIT 100")
    List<Map<String,Object>> improvements();
    @Select("SELECT state,version FROM ai_operations_improvement WHERE improvement_ref=#{ref} FOR UPDATE")
    Map<String,Object> improvement(@Param("ref") String ref);
    @Update("UPDATE ai_operations_improvement SET state=#{state},version=version+1,verification_code=#{verification},actor_ref=#{actor},updated_at=UTC_TIMESTAMP() WHERE improvement_ref=#{ref} AND version=#{version}")
    int updateImprovement(Map<String,Object> request);
    @Insert("INSERT INTO ai_operations_improvement_audit(improvement_ref,version,state,verification_code,actor_ref,created_at) VALUES(#{ref},#{nextVersion},#{state},#{verification},#{actor},UTC_TIMESTAMP())")
    int improvementAudit(Map<String,Object> request);
    @Select("SELECT case_ref AS caseRef FROM ai_handoff_record WHERE projection_cleared=0 AND analysis_attempts<2 AND (analysis_state='PENDING' OR (analysis_state='RUNNING' AND lease_until<UTC_TIMESTAMP())) ORDER BY confirmed_at LIMIT 1 FOR UPDATE")
    Map<String,Object> nextAnalysis();
    @Update("UPDATE ai_handoff_record SET analysis_state='RUNNING',analysis_attempts=analysis_attempts+1,analysis_lease=#{lease},lease_until=DATE_ADD(UTC_TIMESTAMP(),INTERVAL 90 SECOND) WHERE case_ref=#{ref}")
    int lease(@Param("ref") String ref,@Param("lease") String lease);
    @Update("UPDATE ai_handoff_record SET analysis_state=#{state},model_reason=#{reason},analysis_version='v1',analysis_lease=NULL,lease_until=NULL WHERE case_ref=#{ref} AND analysis_lease=#{lease} AND analysis_state='RUNNING' AND projection_cleared=0")
    int finish(@Param("ref") String ref,@Param("lease") String lease,@Param("state") String state,@Param("reason") String reason);
    @Update("UPDATE ai_handoff_record SET analysis_state='UNAVAILABLE',analysis_lease=NULL WHERE analysis_state='RUNNING' AND lease_until<UTC_TIMESTAMP() AND analysis_attempts>=2")
    int expireLeases();
    @Insert("INSERT INTO ai_handoff_analysis_provenance(case_ref,lease_ref,input_hash,taxonomy_version,prompt_version,model_version,created_at) VALUES(#{ref},#{lease},#{hash},'v1','handoff-v1',#{model},UTC_TIMESTAMP())")
    int provenance(@Param("ref") String ref,@Param("lease") String lease,@Param("hash") String hash,@Param("model") String model);
    @Select("SELECT input_hash AS inputHash,taxonomy_version AS taxonomyVersion,prompt_version AS promptVersion,model_version AS modelVersion,created_at AS createdAt FROM ai_handoff_analysis_provenance WHERE case_ref=#{ref} ORDER BY created_at")
    List<Map<String,Object>> provenanceHistory(@Param("ref") String ref);
    @Select("SELECT r.case_ref FROM ai_handoff_record r JOIN ai_service_case c ON c.case_id=r.case_ref LEFT JOIN ai_handoff_retention_hold h ON h.case_ref=r.case_ref WHERE r.projection_cleared=0 AND c.state='CLOSED' AND COALESCE(h.held,0)=0 AND c.updated_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL #{days} DAY) ORDER BY r.case_ref LIMIT 100 FOR UPDATE")
    List<String> retentionCandidates(@Param("days") int days);
    @Update("UPDATE ai_handoff_record SET task_ref=NULL,stage='unknown',projection_cleared=1,analysis_state=IF(analysis_state IN ('PENDING','RUNNING'),'UNAVAILABLE',analysis_state),analysis_lease=NULL,lease_until=NULL WHERE case_ref=#{ref} AND projection_cleared=0")
    int clearOneProjection(@Param("ref") String ref);
    @Select("SELECT e.event_ref FROM ai_handoff_event e LEFT JOIN ai_service_case c ON c.case_id=e.case_ref LEFT JOIN ai_handoff_retention_hold h ON h.case_ref=e.case_ref WHERE e.created_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL #{days} DAY) AND (e.case_ref IS NULL OR c.state='CLOSED') AND COALESCE(h.held,0)=0 ORDER BY e.event_ref LIMIT 100 FOR UPDATE")
    List<String> expiredEvents(@Param("days") int days);
    @Delete("DELETE FROM ai_handoff_event WHERE event_ref=#{ref}")
    int removeEvent(@Param("ref") String ref);
    @Insert("INSERT INTO ai_handoff_retention_audit(audit_ref,actor_ref,projection_days,event_days,projections_cleared,events_removed,created_at) VALUES(#{ref},#{actor},#{days},#{eventDays},#{cleared},#{removed},UTC_TIMESTAMP())")
    int retentionAudit(@Param("ref") String ref,@Param("actor") String actor,@Param("days") int days,@Param("eventDays") int eventDays,@Param("cleared") int cleared,@Param("removed") int removed);
    @Insert("INSERT INTO ai_handoff_retention_hold(case_ref,held,actor_ref,updated_at) VALUES(#{ref},#{held},#{actor},UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE held=VALUES(held),actor_ref=VALUES(actor_ref),updated_at=VALUES(updated_at)")
    int hold(@Param("ref") String ref,@Param("held") boolean held,@Param("actor") String actor);
    @Select("SELECT COUNT(*) FROM ai_handoff_record r JOIN ai_service_case c ON c.case_id=r.case_ref LEFT JOIN ai_handoff_retention_hold h ON h.case_ref=r.case_ref WHERE r.projection_cleared=0 AND COALESCE(h.held,0)=0 AND c.state='CLOSED' AND c.updated_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL #{days} DAY)")
    int retentionCount(@Param("days") int days);
}
