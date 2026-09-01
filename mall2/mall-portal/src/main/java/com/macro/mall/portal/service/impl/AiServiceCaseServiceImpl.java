package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.Asserts;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiServiceCaseDao;
import com.macro.mall.portal.domain.AiServiceCaseCancelRequest;
import com.macro.mall.portal.domain.AiServiceCaseCustomerInformationRequest;
import com.macro.mall.portal.domain.AiServiceCasePublicView;
import com.macro.mall.portal.domain.AiServiceCaseReopenRequest;
import com.macro.mall.portal.domain.AiServiceCaseRecord;
import com.macro.mall.portal.domain.AiServiceCaseTimelineEntry;
import com.macro.mall.portal.service.AiServiceCaseService;
import com.macro.mall.portal.service.UmsMemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Customer actions are deterministic and tied to the current member/version.
 * They neither assign processors nor reveal internal notes or queue data.
 */
@Service
public class AiServiceCaseServiceImpl implements AiServiceCaseService {
    private static final Set<String> INFORMATION_TYPES = new HashSet<>(Arrays.asList(
            "problem_description", "purchase_context"
    ));
    private static final Pattern IDEMPOTENCY_KEY = Pattern.compile("[a-f0-9]{32}");
    private static final Pattern CASE_ID = Pattern.compile("[a-f0-9-]{36}");
    private static final Pattern CORRELATION_REF = Pattern.compile("[a-f0-9]{16,64}");
    private static final Pattern PHONE_LIKE = Pattern.compile("(?<!\\d)1\\d{10}(?!\\d)");
    private static final Pattern BEARER_LIKE = Pattern.compile("(?i)bearer\\s+\\S+");

    @Autowired
    private AiServiceCaseDao serviceCaseDao;
    @Autowired
    private UmsMemberService memberService;

    @Override
    public List<AiServiceCasePublicView> listMine() {
        UmsMember member = requireCurrentMember();
        List<AiServiceCaseRecord> records = serviceCaseDao.listByMemberId(member.getId());
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        java.util.ArrayList<AiServiceCasePublicView> result = new java.util.ArrayList<>();
        for (AiServiceCaseRecord record : records) {
            if (record != null) {
                result.add(AiServiceCasePublicView.from(record));
            }
        }
        return result;
    }

    @Override
    public List<AiServiceCaseTimelineEntry> timelineMine(String caseId) {
        AiServiceCaseRecord record = requireOwnedCase(caseId, requireCurrentMember().getId());
        List<AiServiceCaseTimelineEntry> result = serviceCaseDao.listPublicTimeline(record.getCaseId());
        return result == null ? Collections.emptyList() : result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiServiceCasePublicView submitCustomerInformation(
            String caseId,
            AiServiceCaseCustomerInformationRequest request,
            String correlationRef
    ) {
        UmsMember member = requireCurrentMember();
        AiServiceCaseRecord current = requireOwnedCase(caseId, member.getId());
        validateInformationRequest(request);
        String actorRef = String.valueOf(member.getId());
        if (serviceCaseDao.findActionIdempotent(
                current.getCaseId(), "customer", actorRef, request.getIdempotencyKey().trim()
        ) != null) {
            return AiServiceCasePublicView.from(requireOwnedCase(caseId, member.getId()));
        }
        if (serviceCaseDao.updateCustomerInformationIfVersion(
                current.getCaseId(), member.getId(), request.getExpectedVersion(),
                request.getInformationType().trim(), request.getInformation().trim(),
                "已收到您补充的信息，人工正在继续处理。", "已收到补充信息。"
        ) != 1) {
            throw new IllegalStateException("案件状态已变化，请刷新后重试");
        }
        AiServiceCaseRecord updated = requireOwnedCase(caseId, member.getId());
        insertActionAndOutbox(
                updated, actorRef, "customer_information", request.getExpectedVersion(),
                "accepted", "已收到补充信息。", request.getIdempotencyKey().trim(), correlationRef
        );
        return AiServiceCasePublicView.from(updated);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiServiceCasePublicView cancelMine(
            String caseId,
            AiServiceCaseCancelRequest request,
            String correlationRef
    ) {
        UmsMember member = requireCurrentMember();
        AiServiceCaseRecord current = requireOwnedCase(caseId, member.getId());
        validateCancelRequest(request);
        String actorRef = String.valueOf(member.getId());
        if (serviceCaseDao.findActionIdempotent(
                current.getCaseId(), "customer", actorRef, request.getIdempotencyKey().trim()
        ) != null) {
            return AiServiceCasePublicView.from(requireOwnedCase(caseId, member.getId()));
        }
        if (serviceCaseDao.cancelIfVersion(
                current.getCaseId(), member.getId(), request.getExpectedVersion(),
                "该人工协同事项已取消。", "您已取消该人工协同事项。"
        ) != 1) {
            throw new IllegalStateException("当前案件不允许取消或状态已变化");
        }
        AiServiceCaseRecord updated = requireOwnedCase(caseId, member.getId());
        insertActionAndOutbox(
                updated, actorRef, "customer_cancel", request.getExpectedVersion(),
                "cancelled", "您已取消该人工协同事项。", request.getIdempotencyKey().trim(), correlationRef
        );
        return AiServiceCasePublicView.from(updated);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiServiceCasePublicView reopenMine(
            String caseId,
            AiServiceCaseReopenRequest request,
            String correlationRef
    ) {
        UmsMember member = requireCurrentMember();
        AiServiceCaseRecord current = requireOwnedCase(caseId, member.getId());
        validateReopenRequest(request);
        String actorRef = String.valueOf(member.getId());
        if (serviceCaseDao.findActionIdempotent(
                current.getCaseId(), "customer", actorRef, request.getIdempotencyKey().trim()
        ) != null) {
            return AiServiceCasePublicView.from(requireOwnedCase(caseId, member.getId()));
        }
        if (serviceCaseDao.reopenIfVersion(
                current.getCaseId(), member.getId(), request.getExpectedVersion(), request.getReason().trim(),
                "已重新开启人工协同事项，等待处理人员继续核验。", "已提交重新处理请求。"
        ) != 1) {
            throw new IllegalStateException("当前案件不允许重新开启、已超过处理窗口或状态已变化");
        }
        AiServiceCaseRecord updated = requireOwnedCase(caseId, member.getId());
        insertActionAndOutbox(
                updated, actorRef, "customer_reopen", request.getExpectedVersion(),
                "reopened", "已提交重新处理请求。", request.getIdempotencyKey().trim(), correlationRef
        );
        return AiServiceCasePublicView.from(updated);
    }

    private void insertActionAndOutbox(
            AiServiceCaseRecord updated,
            String actorRef,
            String actionType,
            Integer expectedVersion,
            String resultCode,
            String publicMessage,
            String idempotencyKey,
            String correlationRef
    ) {
        if (serviceCaseDao.insertAction(
                UUID.randomUUID().toString(), updated.getCaseId(), "customer", actorRef, actionType,
                expectedVersion, resultCode, publicMessage, idempotencyKey, safeCorrelationRef(correlationRef)
        ) != 1) {
            throw new IllegalStateException("案件操作审计无法记录");
        }
        if (serviceCaseDao.insertOutbox(
                UUID.randomUUID().toString(), updated.getCaseId(), updated.getMemberId(),
                "service_case_" + actionType, updated.getStateVersion(), safeCorrelationRef(correlationRef)
        ) != 1) {
            throw new IllegalStateException("案件状态事件无法记录");
        }
    }

    private UmsMember requireCurrentMember() {
        UmsMember member = memberService.getCurrentMember();
        if (member == null || member.getId() == null) {
            Asserts.fail("当前用户未登录！");
        }
        return member;
    }

    private AiServiceCaseRecord requireOwnedCase(String caseId, Long memberId) {
        if (caseId == null || !CASE_ID.matcher(caseId).matches()) {
            throw new IllegalArgumentException("案件标识不合法");
        }
        AiServiceCaseRecord record = serviceCaseDao.findByCaseIdAndMemberId(caseId, memberId);
        if (record == null) {
            throw new IllegalArgumentException("案件不存在或不属于当前用户");
        }
        return record;
    }

    private void validateInformationRequest(AiServiceCaseCustomerInformationRequest request) {
        validateVersionAndIdempotency(
                request == null ? null : request.getExpectedVersion(),
                request == null ? null : request.getIdempotencyKey()
        );
        if (request.getInformationType() == null || !INFORMATION_TYPES.contains(request.getInformationType().trim())) {
            throw new IllegalArgumentException("补充信息类型不合法");
        }
        requireSafeCustomerInformation(request.getInformation());
    }

    private void validateCancelRequest(AiServiceCaseCancelRequest request) {
        validateVersionAndIdempotency(
                request == null ? null : request.getExpectedVersion(),
                request == null ? null : request.getIdempotencyKey()
        );
    }

    private void validateReopenRequest(AiServiceCaseReopenRequest request) {
        validateVersionAndIdempotency(
                request == null ? null : request.getExpectedVersion(),
                request == null ? null : request.getIdempotencyKey()
        );
        requireSafeCustomerInformation(request == null ? null : request.getReason());
    }

    private void validateVersionAndIdempotency(Integer version, String idempotencyKey) {
        if (version == null || version < 1) {
            throw new IllegalArgumentException("案件版本不合法");
        }
        if (idempotencyKey == null || !IDEMPOTENCY_KEY.matcher(idempotencyKey.trim()).matches()) {
            throw new IllegalArgumentException("案件操作幂等标识不合法");
        }
    }

    private void requireSafeCustomerInformation(String value) {
        if (value == null || value.trim().isEmpty() || value.trim().length() > 180) {
            throw new IllegalArgumentException("补充信息长度不合法");
        }
        if (PHONE_LIKE.matcher(value).find() || BEARER_LIKE.matcher(value).find()) {
            throw new IllegalArgumentException("请勿在此提交联系方式或凭证信息");
        }
    }

    private String safeCorrelationRef(String value) {
        return value != null && CORRELATION_REF.matcher(value.trim()).matches() ? value.trim() : null;
    }
}
