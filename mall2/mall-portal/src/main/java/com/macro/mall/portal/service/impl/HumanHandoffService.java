package com.macro.mall.portal.service.impl;

import com.macro.mall.portal.dao.HumanHandoffDao;
import com.macro.mall.portal.dao.AiServiceCaseDao;
import com.macro.mall.portal.domain.*;
import com.macro.mall.portal.service.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import java.util.*;

@Service
public class HumanHandoffService {
    @Autowired private HumanHandoffDao dao;
    @Autowired private AiCaseHandoffService legacy;
    @Autowired private UmsMemberService members;
    @Autowired private AiServiceCaseDao cases;

    private Long member() { return members.getCurrentMember().getId(); }
    private void require(boolean condition) {
        if (!condition) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"交接参数不合法");
    }
    private boolean one(String value,String choices) { return value != null && Arrays.asList(choices.split(",")).contains(value); }
    private boolean hash(String value) { return value != null && value.matches("[a-f0-9]{64}"); }

    public Map<String,Object> find(String request) {
        require(hash(request));
        Long owner=member();
        Map<String,Object> result=dao.byRequest(owner,request);
        if(result==null) result=dao.reused(owner,request);
        if(result==null) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"尚未查到交接结果");
        result.remove("contentHash");
        return result;
    }

    @Transactional public void event(String request,String type) {
        require(hash(request)&&one(type,"requested,suggested,cancelled"));
        String event;
        try {
            byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest((request+":"+type).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder hex=new StringBuilder();for(byte value:digest)hex.append(String.format("%02x",value));event=hex.toString();
        } catch(java.security.NoSuchAlgorithmException exc) { throw new IllegalStateException(exc); }
        dao.event(event,member(),request,null,type);
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> create(HumanHandoffRequest r) {
        require(r!=null && hash(r.requestRef) && hash(r.scopeKey) && hash(r.contentHash));
        require(one(r.triggerSource,"customer_requested,system_suggested_accepted"));
        require(one(r.entryChannel,"chat,button,legacy"));
        require(one(r.businessTopic,"logistics,policy,refund,return,exchange,repair,application_follow_up,general,unknown"));
        require(one(r.customerReason,"human_preference,intent_misunderstood,repeated_questions,answer_or_evidence_insufficient,tool_or_system_error,capability_or_permission_limit,business_dispute,delay_or_complex_process,unspecified"));
        require(one(r.stage,"created,planning,executing,replanning,waiting_for_user,waiting_for_async_task,ready_to_commit,committing,completed,failed,blocked,cancelled,waiting_human"));
        require(r.taskRef==null || r.taskRef.matches("taskref-[a-z0-9]{8,32}"));
        require(r.planVersion>=0&&r.planVersion<=99&&r.completedSteps>=0&&r.completedSteps<=12&&r.verifiedEvidenceCount>=0&&r.verifiedEvidenceCount<=1000);
        validateProblem(r.problemProjection);
        validateSnapshot(r.safeInputSnapshot);
        Long owner=member();
        dao.ensureScope(owner,r.scopeKey);
        String active=dao.lockScope(owner,r.scopeKey);
        Map<String,Object> prior=dao.byRequest(owner,r.requestRef);
        if(prior!=null) {
            if(!r.contentHash.equals(prior.get("contentHash"))) throw new ResponseStatusException(HttpStatus.CONFLICT,"同一请求内容冲突");
            prior.remove("contentHash"); return prior;
        }
        Map<String,Object> reused=dao.reused(owner,r.requestRef);
        if(reused!=null) {
            if(!r.contentHash.equals(reused.get("contentHash"))) throw new ResponseStatusException(HttpStatus.CONFLICT,"同一请求内容冲突");
            reused.remove("contentHash"); return reused;
        }
        if(active!=null) {
            Map<String,Object> state=dao.caseState(owner,active);
            if(state!=null && !one(String.valueOf(state.get("state")),"CLOSED,CANCELLED")) {
                dao.bindRequest(owner,r.requestRef,r.contentHash,active);
                dao.event(r.requestRef,owner,r.requestRef,active,"reused"); return state;
            }
        }
        AiCaseHandoffRequest request=new AiCaseHandoffRequest();
        request.setCaseKey(r.requestRef); request.setSourceFlow("customer_requested");
        request.setDiagnosisCategory("facts_incomplete"); request.setEvidenceStatus("insufficient");
        request.setHandoffReason("manual_review"); request.setRequiresHumanReview(true); request.setSchemaVersion("2");
        AiCaseHandoffSummary created=legacy.createOrGetForCurrentMember(request);
        String ref=created.getCaseId();
        dao.insert(owner,ref,r); dao.context(ref,r); dao.bindScope(owner,r.scopeKey,ref);
        if(r.problemProjection!=null)try {
            dao.problem(ref,new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(r.problemProjection),String.valueOf(r.problemProjection.get("projection_hash")),String.valueOf(r.problemProjection.get("content_quality")));
        } catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalArgumentException("问题投影无效");}
        dao.noRedundantModel(ref);
        if(r.safeInputSnapshot!=null)try {
            dao.summaryInput(ref,String.valueOf(r.safeInputSnapshot.get("hash")),new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(r.safeInputSnapshot),"READY".equals(r.safeInputSnapshot.get("quality"))?"PENDING":"INSUFFICIENT_CONTEXT");
            dao.waitForSummary(ref,"READY".equals(r.safeInputSnapshot.get("quality")));
        }catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalArgumentException("安全背景无效");}
        dao.bindRequest(owner,r.requestRef,r.contentHash,ref);
        dao.event(r.requestRef,owner,r.requestRef,ref,"confirmed");
        cases.insertAction(UUID.randomUUID().toString(),ref,"customer","member","handoff_confirmed",1,"QUEUED","已登记，等待人工领取。",r.requestRef.substring(0,32),null);
        return dao.caseState(owner,ref);
    }

    private void validateProblem(Map<String,Object> p) {
        if(p==null)return; // Existing prepared cards remain compatible.
        require(p.keySet().equals(new HashSet<>(Arrays.asList("customer_goal","unresolved_question","customer_statement","issue_codes","verified_fact_codes","evidence_refs","content_quality","redaction_version","summary_template_version","projection_hash"))));
        require(hash(String.valueOf(p.get("projection_hash"))));
        require("closed-phrases-v1".equals(p.get("redaction_version"))&&"issue-v1".equals(p.get("summary_template_version")));
        require(Arrays.asList("了解并办理换货","了解并办理退货","了解并办理退款","了解物流处理","了解适用政策","了解并办理维修","了解申请进度","解决咨询问题").contains(p.get("customer_goal")));
        require("".equals(p.get("customer_statement"))&&Collections.emptyList().equals(p.get("verified_fact_codes"))&&Collections.emptyList().equals(p.get("evidence_refs")));
        require(p.get("issue_codes") instanceof List);
        List<?> codes=(List<?>)p.get("issue_codes");
        List<String> keys=Arrays.asList("materials","entry","eligibility","progress","policy_conflict","system_error");
        List<String> values=Arrays.asList("材料要求不清楚","找不到办理入口","适用资格尚不明确","处理进度不明确","政策说明存在待核实的冲突","办理过程中出现系统异常");
        require(codes.size()<=6&&new HashSet<>(codes).size()==codes.size());
        List<String> phrases=new ArrayList<>();for(Object code:codes){require(keys.contains(code));phrases.add(values.get(keys.indexOf(code)));}
        require(String.join("；",phrases).equals(p.get("unresolved_question")));
        require(codes.isEmpty()?Arrays.asList("INSUFFICIENT_CONTEXT","REDACTION_REJECTED").contains(p.get("content_quality")):"READY".equals(p.get("content_quality")));
        try {
            Map<String,Object> canonical=new TreeMap<>(p);canonical.remove("projection_hash");
            byte[] encoded=new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsBytes(canonical);
            byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(encoded);
            StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format("%02x",b));
            require(hex.toString().equals(p.get("projection_hash")));
        } catch(java.security.NoSuchAlgorithmException|com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalStateException("投影校验不可用");}
    }
    private void validateSnapshot(Map<String,Object> s){
        if(s==null)return;
        require(s.keySet().equals(new HashSet<>(Arrays.asList("version","fragments","omitted","truncated","scope","quality","hash"))));
        require("safe-lexemes-v1".equals(s.get("version"))&&hash(String.valueOf(s.get("hash"))));
        require(s.get("fragments") instanceof List&&((List<?>)s.get("fragments")).size()<=8);
        require(Arrays.asList("READY","INSUFFICIENT_CONTEXT").contains(s.get("quality")));
        require(s.get("omitted") instanceof Boolean&&s.get("truncated") instanceof Boolean);
        require(Arrays.asList("task","conversation").contains(s.get("scope")));
        int length=0;
        for(Object item:(List<?>)s.get("fragments")){
            require(item instanceof Map);Map<?,?> f=(Map<?,?>)item;
            require(f.keySet().equals(new HashSet<>(Arrays.asList("ref","kind","text","version"))));
            require("safe-lexemes-v1".equals(f.get("version")));
            require(String.valueOf(f.get("ref")).matches("src-[a-f0-9]{24}"));
            require(Arrays.asList("customer_statement","assistant_explanation","execution_result").contains(f.get("kind")));
            String text=String.valueOf(f.get("text"));length+=text.length();require(text.length()<=1000&&text.matches("[\\p{IsHan} ]+"));
            require(!text.matches(".*(密码|密钥|身份证|电话|住址|地址|姓名).*"));
        }
        require(length<=3000);
        boolean customer=((List<Map<String,Object>>)s.get("fragments")).stream().anyMatch(f->"customer_statement".equals(f.get("kind")));
        require(customer=="READY".equals(s.get("quality")));
        try{
            Map<String,Object> canonical=new TreeMap<>(s);canonical.remove("hash");
            com.fasterxml.jackson.databind.ObjectMapper mapper=new com.fasterxml.jackson.databind.ObjectMapper().configure(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS,true);
            byte[] bytes=mapper.writeValueAsBytes(canonical);require(bytes.length<=6000);
            byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format("%02x",b));require(hex.toString().equals(s.get("hash")));
        }catch(java.security.NoSuchAlgorithmException|com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalStateException("快照校验不可用");}
    }
}
