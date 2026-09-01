package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.Asserts;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiCaseHandoffDao;
import com.macro.mall.portal.dao.AiServiceCaseDao;
import com.macro.mall.portal.domain.AiCaseHandoffRecord;
import com.macro.mall.portal.domain.AiCaseHandoffRequest;
import com.macro.mall.portal.domain.AiCaseHandoffSummary;
import com.macro.mall.portal.domain.AiServiceCaseRecord;
import com.macro.mall.portal.domain.AiServiceCaseRoutingRule;
import com.macro.mall.portal.service.AiCaseHandoffService;
import com.macro.mall.portal.service.UmsMemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * The portal remains the authorization authority for member-scoped handoffs.
 * The AI service cannot submit a member id and cannot persist free-form text.
 */
@Service
public class AiCaseHandoffServiceImpl implements AiCaseHandoffService {
    private static final Set<String> DIAGNOSIS_CATEGORIES = new HashSet<>(Arrays.asList(
            "delivery_in_transit", "delivery_exception", "order_state_review",
            "facts_incomplete", "policy_consultation", "policy_insufficient", "tool_failure", "needs_order_identifier"
    ));
    private static final Set<String> EVIDENCE_STATUSES = new HashSet<>(Arrays.asList(
            "complete", "partial", "insufficient", "unavailable"
    ));
    private static final Set<String> HANDOFF_REASONS = new HashSet<>(Arrays.asList(
            "tool_failure", "insufficient_evidence", "manual_review"
    ));

    @Autowired
    private AiCaseHandoffDao aiCaseHandoffDao;
    @Autowired
    private UmsMemberService memberService;
    @Autowired
    private AiServiceCaseDao serviceCaseDao;

    private static final Pattern CORRELATION_REF = Pattern.compile("[a-f0-9]{16,64}");

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiCaseHandoffSummary createOrGetForCurrentMember(AiCaseHandoffRequest request) {
        validate(request);
        UmsMember member = memberService.getCurrentMember();
        if (member == null || member.getId() == null) {
            Asserts.fail("当前用户未登录！");
        }

        AiCaseHandoffRecord existing = aiCaseHandoffDao.findByMemberIdAndCaseKey(
                member.getId(), request.getCaseKey().trim()
        );
        if (existing != null) {
            ensureQueuedServiceCase(existing, member.getId(), request.getCorrelationRef());
            return AiCaseHandoffSummary.from(existing);
        }

        AiCaseHandoffRecord record = new AiCaseHandoffRecord();
        record.setCaseId(UUID.randomUUID().toString());
        record.setMemberId(member.getId());
        record.setCaseKey(request.getCaseKey().trim());
        record.setSourceFlow("customer_diagnosis");
        record.setDiagnosisCategory(request.getDiagnosisCategory().trim());
        record.setEvidenceStatus(request.getEvidenceStatus().trim());
        record.setHandoffReason(request.getHandoffReason().trim());
        record.setRequiresHumanReview(true);
        record.setCaseStatus("OPEN");
        record.setSchemaVersion("1");
        if (aiCaseHandoffDao.insertIgnore(record) != 1) {
            AiCaseHandoffRecord concurrent = aiCaseHandoffDao.findByMemberIdAndCaseKey(
                    member.getId(), request.getCaseKey().trim()
            );
            if (concurrent == null) {
                Asserts.fail("人工跟进暂时无法登记，请稍后重试。");
            }
            ensureQueuedServiceCase(concurrent, member.getId(), request.getCorrelationRef());
            return AiCaseHandoffSummary.from(concurrent);
        }
        AiCaseHandoffRecord created = aiCaseHandoffDao.findByMemberIdAndCaseKey(
                member.getId(), request.getCaseKey().trim()
        );
        if (created == null) {
            Asserts.fail("人工跟进暂时无法登记，请稍后重试。");
        }
        ensureQueuedServiceCase(created, member.getId(), request.getCorrelationRef());
        return AiCaseHandoffSummary.from(created);
    }

    private void ensureQueuedServiceCase(
            AiCaseHandoffRecord handoff,
            Long memberId,
            String correlationRef
    ) {
        AiServiceCaseRecord existingCase = serviceCaseDao.findByMemberIdAndCaseKey(memberId, handoff.getCaseKey());
        if (existingCase != null) {
            return;
        }
        AiServiceCaseRoutingRule route = serviceCaseDao.findActiveRoutingRule(handoff.getDiagnosisCategory());
        if (route == null || route.getEligibleQueueRef() == null || route.getPriority() == null) {
            throw new IllegalStateException("人工协同路由规则不可用");
        }
        AiServiceCaseRecord candidate = new AiServiceCaseRecord();
        candidate.setCaseId(handoff.getCaseId());
        candidate.setMemberId(memberId);
        candidate.setCaseKey(handoff.getCaseKey());
        candidate.setQueueRef(route.getEligibleQueueRef());
        candidate.setDiagnosisCategory(handoff.getDiagnosisCategory());
        candidate.setPriority(route.getPriority());
        candidate.setState("QUEUED");
        candidate.setStateVersion(1);
        candidate.setPublicStatus("已转人工处理，等待处理人员领取。");
        candidate.setLastPublicMessage("已创建人工协同事项。");
        if (serviceCaseDao.insertIgnoreCase(candidate) == 1) {
            if (serviceCaseDao.insertOutbox(
                    UUID.randomUUID().toString(), candidate.getCaseId(), memberId,
                    "service_case_queued", 1, safeCorrelationRef(correlationRef)
            ) != 1) {
                throw new IllegalStateException("人工协同事件无法记录");
            }
        }
    }

    private void validate(AiCaseHandoffRequest request) {
        if (request == null || !isSha256(request.getCaseKey())) {
            Asserts.fail("人工跟进标识不合法！");
        }
        if (!"customer_diagnosis".equals(request.getSourceFlow())) {
            Asserts.fail("人工跟进来源不合法！");
        }
        if (!DIAGNOSIS_CATEGORIES.contains(request.getDiagnosisCategory())) {
            Asserts.fail("诊断分类不合法！");
        }
        if (!EVIDENCE_STATUSES.contains(request.getEvidenceStatus())) {
            Asserts.fail("证据状态不合法！");
        }
        if (!HANDOFF_REASONS.contains(request.getHandoffReason())) {
            Asserts.fail("人工跟进原因不合法！");
        }
        if (!Boolean.TRUE.equals(request.getRequiresHumanReview())) {
            Asserts.fail("人工跟进标记不合法！");
        }
        if (!"1".equals(request.getSchemaVersion())) {
            Asserts.fail("人工跟进协议版本不合法！");
        }
    }

    private boolean isSha256(String value) {
        return value != null && value.matches("[a-f0-9]{64}");
    }

    private String safeCorrelationRef(String value) {
        return value != null && CORRELATION_REF.matcher(value.trim()).matches() ? value.trim() : null;
    }
}
