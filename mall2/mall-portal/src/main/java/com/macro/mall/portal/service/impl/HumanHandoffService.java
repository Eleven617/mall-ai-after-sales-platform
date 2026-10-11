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
        dao.bindRequest(owner,r.requestRef,r.contentHash,ref);
        dao.event(r.requestRef,owner,r.requestRef,ref,"confirmed");
        cases.insertAction(UUID.randomUUID().toString(),ref,"customer","member","handoff_confirmed",1,"QUEUED","已登记，等待人工领取。",r.requestRef.substring(0,32),null);
        return dao.caseState(owner,ref);
    }
}
