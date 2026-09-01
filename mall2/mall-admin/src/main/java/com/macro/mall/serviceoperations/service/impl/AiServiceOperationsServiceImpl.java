package com.macro.mall.serviceoperations.service.impl;

import com.macro.mall.serviceoperations.dao.AiServiceOperationsDao;
import com.macro.mall.serviceoperations.domain.AiServiceCaseActionRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseClaimRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorRecord;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorView;
import com.macro.mall.serviceoperations.service.AiServiceOperationsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Deterministic human case handling. Neither a browser nor a model can select
 * an assignee or skip expected-version, idempotency, audit, or Outbox writes.
 */
@Service
public class AiServiceOperationsServiceImpl implements AiServiceOperationsService {
    private static final Set<String> ALLOWED_QUEUES = new HashSet<>(Arrays.asList(
            "logistics_review", "policy_review", "general_after_sales"
    ));
    private static final Set<String> INFORMATION_TYPES = new HashSet<>(Arrays.asList(
            "problem_description", "purchase_context"
    ));
    private static final Pattern CASE_ID = Pattern.compile("[a-f0-9-]{36}");
    private static final Pattern IDEMPOTENCY_KEY = Pattern.compile("[a-f0-9]{32}");
    private static final Pattern CORRELATION_REF = Pattern.compile("[a-f0-9]{16,64}");
    private static final Pattern PHONE_LIKE = Pattern.compile("(?<!\\d)1\\d{10}(?!\\d)");
    private static final Pattern BEARER_LIKE = Pattern.compile("(?i)bearer\\s+\\S+");

    @Autowired
    private AiServiceOperationsDao serviceOperationsDao;

    @Override
    public List<AiServiceCaseProcessorView> listVisible(String username, Integer limit) {
        String processor = requireProcessor(username);
        int boundedLimit = limit == null ? 20 : Math.max(1, Math.min(50, limit));
        List<AiServiceCaseProcessorRecord> records = serviceOperationsDao.listVisibleForProcessor(processor, boundedLimit);
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        List<AiServiceCaseProcessorView> result = new ArrayList<>();
        for (AiServiceCaseProcessorRecord record : records) {
            if (record != null && isAllowedQueue(record.getQueueRef())) {
                result.add(AiServiceCaseProcessorView.from(record, processor));
            }
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiServiceCaseProcessorView claim(
            String caseId,
            AiServiceCaseClaimRequest request,
            String username,
            String correlationRef
    ) {
        String processor = requireProcessor(username);
        validateCaseId(caseId);
        validateVersionAndIdempotency(
                request == null ? null : request.getExpectedVersion(),
                request == null ? null : request.getIdempotencyKey()
        );
        String idempotencyKey = request.getIdempotencyKey().trim();
        if (serviceOperationsDao.findActionIdempotent(caseId, "processor", processor, idempotencyKey) != null) {
            return viewForAssignedOrQueued(requireCase(caseId), processor);
        }
        AiServiceCaseProcessorRecord current = requireCase(caseId);
        requireAllowedQueue(current);
        if (serviceOperationsDao.claimIfVersion(
                caseId, processor, request.getExpectedVersion(),
                "人工处理人员已领取，正在核验。", "人工已开始处理该事项。"
        ) != 1) {
            throw new IllegalStateException("案件已被领取、状态已变化或版本不一致，请刷新后重试");
        }
        AiServiceCaseProcessorRecord updated = requireCase(caseId);
        requireAssigned(updated, processor);
        recordActionAndOutbox(
                updated, processor, "claim", request.getExpectedVersion(), "claimed",
                "人工已开始处理该事项。", null, idempotencyKey, correlationRef
        );
        return AiServiceCaseProcessorView.from(updated, processor);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiServiceCaseProcessorView act(
            String caseId,
            AiServiceCaseActionRequest request,
            String username,
            String correlationRef
    ) {
        String processor = requireProcessor(username);
        validateCaseId(caseId);
        validateVersionAndIdempotency(
                request == null ? null : request.getExpectedVersion(),
                request == null ? null : request.getIdempotencyKey()
        );
        String idempotencyKey = request.getIdempotencyKey().trim();
        if (serviceOperationsDao.findActionIdempotent(caseId, "processor", processor, idempotencyKey) != null) {
            return viewForAssignedOrQueued(requireCase(caseId), processor);
        }
        AiServiceCaseProcessorRecord current = requireCase(caseId);
        requireAllowedQueue(current);
        requireAssigned(current, processor);
        Transition transition = transitionFor(current.getState(), request);
        if (serviceOperationsDao.transitionAssignedIfVersion(
                caseId, processor, request.getExpectedVersion(), current.getState(), transition.targetState,
                transition.informationType,
                transition.publicStatus, transition.publicMessage
        ) != 1) {
            throw new IllegalStateException("案件状态已变化或版本不一致，请刷新后重试");
        }
        AiServiceCaseProcessorRecord updated = requireCase(caseId);
        recordActionAndOutbox(
                updated, processor, transition.actionType, request.getExpectedVersion(), transition.resultCode,
                transition.publicMessage, safeInternalNote(request.getInternalNote()), idempotencyKey, correlationRef
        );
        return AiServiceCaseProcessorView.from(updated, processor);
    }

    private Transition transitionFor(String currentState, AiServiceCaseActionRequest request) {
        String action = request == null || request.getAction() == null ? "" : request.getAction().trim();
        if ("request_information".equals(action)) {
            if (!"CLAIMED".equals(currentState) && !"IN_REVIEW".equals(currentState)) {
                throw new IllegalStateException("当前案件不允许请求补件");
            }
            if (request.getInformationType() == null || !INFORMATION_TYPES.contains(request.getInformationType().trim())) {
                throw new IllegalArgumentException("补件类型不合法");
            }
            return new Transition(
                    "request_information", "AWAITING_CUSTOMER_INFORMATION", "awaiting_customer_information",
                    request.getInformationType().trim(), "等待您补充必要信息后继续处理。",
                    requireSafePublicMessage(request.getPublicMessage())
            );
        }
        if ("start_review".equals(action)) {
            if (!"CLAIMED".equals(currentState) && !"REOPENED".equals(currentState)) {
                throw new IllegalStateException("当前案件不允许进入核验");
            }
            return new Transition(
                    "start_review", "IN_REVIEW", "in_review", null, "人工正在继续核验该事项。",
                    optionalSafePublicMessage(request.getPublicMessage(), "人工正在继续核验该事项。")
            );
        }
        if ("resolve".equals(action)) {
            if (!"IN_REVIEW".equals(currentState)) {
                throw new IllegalStateException("当前案件不允许标记为已处理");
            }
            return new Transition(
                    "resolve", "RESOLVED", "resolved", null, "人工已给出处理结果，如仍有问题可在限定时间内重新开启。",
                    requireSafePublicMessage(request.getPublicMessage())
            );
        }
        if ("close".equals(action)) {
            if (!"RESOLVED".equals(currentState)) {
                throw new IllegalStateException("只有已处理案件可以结案");
            }
            return new Transition(
                    "close", "CLOSED", "closed", null, "人工协同事项已结案。",
                    requireSafePublicMessage(request.getPublicMessage())
            );
        }
        throw new IllegalArgumentException("人工处理动作不合法");
    }

    private void recordActionAndOutbox(
            AiServiceCaseProcessorRecord updated,
            String processor,
            String actionType,
            Integer expectedVersion,
            String resultCode,
            String publicMessage,
            String internalNote,
            String idempotencyKey,
            String correlationRef
    ) {
        if (serviceOperationsDao.insertAction(
                UUID.randomUUID().toString(), updated.getCaseId(), processor, actionType, expectedVersion,
                resultCode, publicMessage, internalNote, idempotencyKey, safeCorrelationRef(correlationRef)
        ) != 1) {
            throw new IllegalStateException("案件操作审计无法记录");
        }
        if (serviceOperationsDao.insertOutbox(
                UUID.randomUUID().toString(), updated.getCaseId(), updated.getMemberId(),
                "service_case_" + actionType, updated.getStateVersion(), safeCorrelationRef(correlationRef)
        ) != 1) {
            throw new IllegalStateException("案件状态事件无法记录");
        }
    }

    private AiServiceCaseProcessorRecord requireCase(String caseId) {
        AiServiceCaseProcessorRecord record = serviceOperationsDao.findByCaseId(caseId);
        if (record == null) {
            throw new IllegalArgumentException("案件不存在");
        }
        return record;
    }

    private AiServiceCaseProcessorView viewForAssignedOrQueued(
            AiServiceCaseProcessorRecord record,
            String processor
    ) {
        requireAllowedQueue(record);
        if (!"QUEUED".equals(record.getState()) && !processor.equals(record.getAssigneeRef())) {
            throw new IllegalArgumentException("案件不存在或不属于当前处理人员");
        }
        return AiServiceCaseProcessorView.from(record, processor);
    }

    private void requireAssigned(AiServiceCaseProcessorRecord record, String processor) {
        if (!processor.equals(record.getAssigneeRef())) {
            throw new IllegalArgumentException("案件不存在或不属于当前处理人员");
        }
    }

    private void requireAllowedQueue(AiServiceCaseProcessorRecord record) {
        if (!isAllowedQueue(record.getQueueRef())) {
            throw new IllegalArgumentException("当前处理人员无权处理该队列");
        }
    }

    private boolean isAllowedQueue(String queueRef) {
        return queueRef != null && ALLOWED_QUEUES.contains(queueRef);
    }

    private String requireProcessor(String username) {
        if (username == null || username.trim().isEmpty() || username.trim().length() > 64) {
            throw new IllegalArgumentException("处理人员身份不可用");
        }
        return username.trim();
    }

    private void validateCaseId(String caseId) {
        if (caseId == null || !CASE_ID.matcher(caseId).matches()) {
            throw new IllegalArgumentException("案件标识不合法");
        }
    }

    private void validateVersionAndIdempotency(Integer version, String idempotencyKey) {
        if (version == null || version < 1) {
            throw new IllegalArgumentException("案件版本不合法");
        }
        if (idempotencyKey == null || !IDEMPOTENCY_KEY.matcher(idempotencyKey.trim()).matches()) {
            throw new IllegalArgumentException("案件操作幂等标识不合法");
        }
    }

    private String requireSafePublicMessage(String value) {
        if (value == null || value.trim().isEmpty() || value.trim().length() > 500) {
            throw new IllegalArgumentException("客户可见说明长度不合法");
        }
        return rejectSensitiveText(value.trim(), "客户可见说明");
    }

    private String optionalSafePublicMessage(String value, String fallback) {
        return value == null || value.trim().isEmpty() ? fallback : requireSafePublicMessage(value);
    }

    private String safeInternalNote(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        if (value.trim().length() > 500) {
            throw new IllegalArgumentException("内部备注长度不合法");
        }
        return rejectSensitiveText(value.trim(), "内部备注");
    }

    private String rejectSensitiveText(String value, String label) {
        if (PHONE_LIKE.matcher(value).find() || BEARER_LIKE.matcher(value).find()) {
            throw new IllegalArgumentException(label + "不得包含联系方式或凭证信息");
        }
        return value;
    }

    private String safeCorrelationRef(String value) {
        return value != null && CORRELATION_REF.matcher(value.trim()).matches() ? value.trim() : null;
    }

    private static final class Transition {
        private final String actionType;
        private final String targetState;
        private final String resultCode;
        private final String informationType;
        private final String publicStatus;
        private final String publicMessage;

        private Transition(
                String actionType,
                String targetState,
                String resultCode,
                String informationType,
                String publicStatus,
                String publicMessage
        ) {
            this.actionType = actionType;
            this.targetState = targetState;
            this.resultCode = resultCode;
            this.informationType = informationType;
            this.publicStatus = publicStatus;
            this.publicMessage = publicMessage;
        }
    }
}
