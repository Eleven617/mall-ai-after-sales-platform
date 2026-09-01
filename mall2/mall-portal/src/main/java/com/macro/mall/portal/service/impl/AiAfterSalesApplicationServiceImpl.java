package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.Asserts;
import com.macro.mall.mapper.OmsOrderItemMapper;
import com.macro.mall.mapper.OmsOrderMapper;
import com.macro.mall.model.OmsOrder;
import com.macro.mall.model.OmsOrderExample;
import com.macro.mall.model.OmsOrderItem;
import com.macro.mall.model.OmsOrderItemExample;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiAfterSalesApplicationDao;
import com.macro.mall.portal.dao.AiAfterSalesActionDao;
import com.macro.mall.portal.dao.AiAfterSalesFulfillmentCallbackDao;
import com.macro.mall.portal.dao.AiAfterSalesOutboxDao;
import com.macro.mall.portal.domain.AiAfterSalesApplicationRecord;
import com.macro.mall.portal.domain.AiAfterSalesApplicationStatus;
import com.macro.mall.portal.domain.AiAfterSalesApplicationSummary;
import com.macro.mall.portal.domain.AiAfterSalesApplicationType;
import com.macro.mall.portal.domain.AiAfterSalesActionRecord;
import com.macro.mall.portal.domain.AiAfterSalesActionRequest;
import com.macro.mall.portal.domain.AiAfterSalesActionStatus;
import com.macro.mall.portal.domain.AiAfterSalesApplyRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilityRequest;
import com.macro.mall.portal.domain.AiAfterSalesEligibilitySummary;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRecord;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentCallbackRequest;
import com.macro.mall.portal.domain.AiAfterSalesFulfillmentStatus;
import com.macro.mall.portal.domain.AiAfterSalesOutboxEvent;
import com.macro.mall.portal.domain.AiAfterSalesSubmissionStatus;
import com.macro.mall.portal.service.AiAfterSalesApplicationService;
import com.macro.mall.portal.service.OmsPortalOrderService;
import com.macro.mall.portal.service.UmsMemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Java-owned after-sales core. A successful "eligible" result only permits
 * creating a pending review request. It does not pretend that payment refunds,
 * warehouse receipts, replacement shipments, or repair fulfillment happened.
 */
@Service
public class AiAfterSalesApplicationServiceImpl implements AiAfterSalesApplicationService {
    private static final String EVENT_CREATED = "after_sales_application_created";
    private static final String EVENT_CANCELLED = "after_sales_application_cancelled";
    private static final String EVENT_MODIFIED = "after_sales_application_modified";
    private static final String SOURCE_UNIFIED_AFTER_SALES = "unified_after_sales";

    @Autowired
    private UmsMemberService memberService;
    @Autowired
    private OmsOrderMapper orderMapper;
    @Autowired
    private OmsOrderItemMapper orderItemMapper;
    @Autowired
    private AiAfterSalesApplicationDao applicationDao;
    @Autowired
    private AiAfterSalesActionDao actionDao;
    @Autowired
    private AiAfterSalesFulfillmentCallbackDao fulfillmentCallbackDao;
    @Autowired
    private AiAfterSalesOutboxDao outboxDao;
    @Autowired
    private OmsPortalOrderService portalOrderService;

    @Override
    public AiAfterSalesEligibilitySummary checkEligibility(AiAfterSalesEligibilityRequest request) {
        AiAfterSalesApplicationType type = validateEligibilityRequest(request);
        UmsMember member = requireCurrentMember();
        OmsOrder order = getCurrentMemberOrder(request.getOrderSn(), member.getId());
        OmsOrderItem item = resolveItemForEligibility(order, type, request.getOrderItemId());
        return assessEligibility(member, order, item, type);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiAfterSalesApplicationSummary createForAi(AiAfterSalesApplyRequest request) {
        AiAfterSalesApplicationType type = validateApplyRequest(request);
        UmsMember member = requireCurrentMember();
        String idempotencyKey = request.getIdempotencyKey().trim();
        String fingerprint = requestFingerprint(request, type);

        AiAfterSalesApplicationRecord existing = applicationDao
                .findByMemberIdAndIdempotencyKey(member.getId(), idempotencyKey);
        if (existing != null) {
            return replayExistingSubmission(existing, fingerprint);
        }

        OmsOrder order = getCurrentMemberOrder(request.getOrderSn(), member.getId());
        OmsOrderItem item = type.isProductRequired()
                ? getOrderItem(order.getId(), request.getOrderItemId())
                : null;
        AiAfterSalesEligibilitySummary eligibility = assessEligibility(member, order, item, type);
        if (!eligibility.isEligible()) {
            Asserts.fail(eligibility.getMessage());
        }

        AiAfterSalesApplicationRecord record = new AiAfterSalesApplicationRecord();
        record.setMemberId(member.getId());
        record.setOrderId(order.getId());
        record.setOrderItemId(item == null ? null : item.getId());
        record.setOrderSn(order.getOrderSn());
        record.setApplicationType(type.getValue());
        record.setProductName(item == null ? "整笔订单" : item.getProductName());
        record.setProductAttr(item == null ? null : item.getProductAttr());
        record.setReason(request.getReason().trim());
        record.setDescription(normalizeDescription(request.getDescription()));
        record.setCustomerSupplement(null);
        boolean directUnpaidCancellation = type == AiAfterSalesApplicationType.CANCEL_REFUND
                && Integer.valueOf(0).equals(order.getStatus());
        record.setStatus((directUnpaidCancellation
                ? AiAfterSalesApplicationStatus.COMPLETED
                : AiAfterSalesApplicationStatus.PENDING_REVIEW).getDatabaseValue());
        record.setStatusNote(directUnpaidCancellation ? "未支付订单已取消" : null);
        record.setFulfillmentStatus((directUnpaidCancellation
                ? AiAfterSalesFulfillmentStatus.SUCCEEDED
                : AiAfterSalesFulfillmentStatus.NOT_STARTED).getDatabaseValue());
        record.setFulfillmentNote(directUnpaidCancellation ? "订单取消已由本地订单服务完成" : "等待审核受理后创建履约任务");
        record.setFulfillmentUpdatedAt(null);
        record.setApplicationKey(directUnpaidCancellation
                ? sha256("cancel-unpaid:" + member.getId() + ":" + order.getId())
                : UUID.randomUUID().toString());
        record.setOpenScopeKey(directUnpaidCancellation
                ? null
                : openScopeKey(member.getId(), order.getId(), item, type));
        record.setIdempotencyKey(idempotencyKey);
        record.setRequestFingerprint(fingerprint);

        if (applicationDao.insertIgnore(record) != 1) {
            AiAfterSalesApplicationRecord concurrent = applicationDao
                    .findByMemberIdAndIdempotencyKey(member.getId(), idempotencyKey);
            if (concurrent != null) {
                return replayExistingSubmission(concurrent, fingerprint);
            }
            AiAfterSalesApplicationRecord active = applicationDao
                    .findByOpenScopeKey(record.getOpenScopeKey());
            if (active != null) {
                Asserts.fail("该订单已有同类型的待审核售后申请！");
            }
            Asserts.fail("售后申请提交正在处理中，请稍后查询提交结果！");
        }
        AiAfterSalesApplicationRecord persisted = applicationDao
                .findByMemberIdAndIdempotencyKey(member.getId(), idempotencyKey);
        if (persisted == null) {
            Asserts.fail("售后申请提交结果无法确认！");
        }
        record = persisted;

        if (directUnpaidCancellation) {
            portalOrderService.cancelOrder(order.getId());
            OmsOrder cancelledOrder = orderMapper.selectByPrimaryKey(order.getId());
            if (cancelledOrder == null || !Integer.valueOf(4).equals(cancelledOrder.getStatus())) {
                Asserts.fail("订单取消未完成，请稍后重试！");
            }
        }

        enqueueEvent(member.getId(), record.getId(), EVENT_CREATED);
        return AiAfterSalesApplicationSummary.from(record);
    }

    @Override
    public AiAfterSalesSubmissionStatus getSubmissionStatus(String idempotencyKey) {
        if (!isValidIdempotencyKey(idempotencyKey)) {
            Asserts.fail("售后提交标识不合法！");
        }
        UmsMember member = requireCurrentMember();
        AiAfterSalesApplicationRecord record = applicationDao
                .findByMemberIdAndIdempotencyKey(member.getId(), idempotencyKey.trim());
        if (record == null) {
            return AiAfterSalesSubmissionStatus.notFound();
        }
        return AiAfterSalesSubmissionStatus.created(AiAfterSalesApplicationSummary.from(record));
    }

    @Override
    public List<AiAfterSalesApplicationSummary> listForAiCurrentMember() {
        UmsMember member = requireCurrentMember();
        List<AiAfterSalesApplicationRecord> records = applicationDao.listByMemberId(member.getId());
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        List<AiAfterSalesApplicationSummary> summaries = new ArrayList<>();
        for (AiAfterSalesApplicationRecord record : records) {
            if (record != null) {
                summaries.add(AiAfterSalesApplicationSummary.from(record));
            }
        }
        return summaries;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiAfterSalesApplicationSummary cancelForAiCurrentMember(
            Long applicationId,
            AiAfterSalesActionRequest request
    ) {
        validateActionRequest(applicationId, request, "cancel");
        UmsMember member = requireCurrentMember();
        AiAfterSalesActionRecord replay = actionDao
                .findByMemberIdAndActionId(member.getId(), request.getActionId().trim());
        if (replay != null) {
            return replayAction(replay, applicationId, request, "cancel", member.getId());
        }
        if (applicationDao.cancelPending(applicationId, member.getId()) != 1) {
            AiAfterSalesActionRecord concurrent = actionDao
                    .findByMemberIdAndActionId(member.getId(), request.getActionId().trim());
            if (concurrent != null) {
                return replayAction(concurrent, applicationId, request, "cancel", member.getId());
            }
            AiAfterSalesApplicationRecord existing = applicationDao
                    .findByIdAndMemberId(applicationId, member.getId());
            if (existing == null) {
                Asserts.fail("售后申请不存在或无权访问！");
            }
            Asserts.fail("当前售后申请已无法取消！");
        }
        AiAfterSalesApplicationRecord cancelled = applicationDao
                .findByIdAndMemberId(applicationId, member.getId());
        if (cancelled == null) {
            Asserts.fail("售后申请取消结果无法确认！");
        }
        persistCompletedAction(member.getId(), applicationId, request, "cancel");
        enqueueEvent(member.getId(), applicationId, EVENT_CANCELLED);
        return AiAfterSalesApplicationSummary.from(cancelled);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiAfterSalesApplicationSummary modifyForAiCurrentMember(
            Long applicationId,
            AiAfterSalesActionRequest request
    ) {
        validateActionRequest(applicationId, request, "modify");
        UmsMember member = requireCurrentMember();
        AiAfterSalesActionRecord replay = actionDao
                .findByMemberIdAndActionId(member.getId(), request.getActionId().trim());
        if (replay != null) {
            return replayAction(replay, applicationId, request, "modify", member.getId());
        }
        AiAfterSalesApplicationRecord existing = applicationDao
                .findByIdAndMemberId(applicationId, member.getId());
        if (existing == null) {
            Asserts.fail("售后申请不存在或无权访问！");
        }
        if (AiAfterSalesApplicationStatus.PENDING_REVIEW.getDatabaseValue()
                .equals(existing.getStatus())) {
            String reason = isBlank(request.getReason()) ? existing.getReason() : request.getReason().trim();
            String description = request.getDescription() == null
                    ? normalizeDescription(existing.getDescription())
                    : normalizeDescription(request.getDescription());
            validateNarrative(reason, description);
            if (applicationDao.modifyPending(applicationId, member.getId(), reason, description) != 1) {
                AiAfterSalesActionRecord concurrent = actionDao
                        .findByMemberIdAndActionId(member.getId(), request.getActionId().trim());
                if (concurrent != null) {
                    return replayAction(concurrent, applicationId, request, "modify", member.getId());
                }
                Asserts.fail("售后申请修改未完成，请稍后重试！");
            }
        } else if (AiAfterSalesApplicationStatus.ACCEPTED.getDatabaseValue()
                .equals(existing.getStatus())) {
            if (!isBlank(request.getReason()) || isBlank(request.getDescription())) {
                Asserts.fail("已受理申请只能补充说明，不能修改原售后原因！");
            }
            if (AiAfterSalesFulfillmentStatus.SUCCEEDED.getDatabaseValue()
                    .equals(existing.getFulfillmentStatus())) {
                Asserts.fail("履约已完成的售后申请不能继续补充说明！");
            }
            String supplement = normalizeDescription(request.getDescription());
            if (supplement.length() > 500) {
                Asserts.fail("补充说明不能超过500个字符！");
            }
            if (applicationDao.supplementAccepted(applicationId, member.getId(), supplement) != 1) {
                AiAfterSalesActionRecord concurrent = actionDao
                        .findByMemberIdAndActionId(member.getId(), request.getActionId().trim());
                if (concurrent != null) {
                    return replayAction(concurrent, applicationId, request, "modify", member.getId());
                }
                Asserts.fail("售后补充说明未完成，请稍后重试！");
            }
        } else {
            Asserts.fail("当前售后申请已无法修改！");
        }
        AiAfterSalesApplicationRecord modified = applicationDao
                .findByIdAndMemberId(applicationId, member.getId());
        if (modified == null) {
            Asserts.fail("售后申请修改结果无法确认！");
        }
        persistCompletedAction(member.getId(), applicationId, request, "modify");
        enqueueEvent(member.getId(), applicationId, EVENT_MODIFIED);
        return AiAfterSalesApplicationSummary.from(modified);
    }

    @Override
    public AiAfterSalesActionStatus getActionStatus(String actionId) {
        if (!isValidIdempotencyKey(actionId)) {
            Asserts.fail("售后操作确认标识不合法！");
        }
        UmsMember member = requireCurrentMember();
        AiAfterSalesActionRecord action = actionDao
                .findByMemberIdAndActionId(member.getId(), actionId.trim());
        if (action == null) {
            return AiAfterSalesActionStatus.notFound();
        }
        AiAfterSalesApplicationRecord application = applicationDao
                .findByIdAndMemberId(action.getApplicationId(), member.getId());
        if (application == null) {
            Asserts.fail("售后操作结果无法确认！");
        }
        return AiAfterSalesActionStatus.completed(AiAfterSalesApplicationSummary.from(application));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiAfterSalesApplicationSummary recordFulfillmentCallback(
            AiAfterSalesFulfillmentCallbackRequest request
    ) {
        validateFulfillmentCallback(request);
        AiAfterSalesFulfillmentCallbackRecord existingCallback = fulfillmentCallbackDao
                .findByCallbackEventId(request.getCallbackEventId().trim());
        if (existingCallback != null) {
            return replayFulfillmentCallback(existingCallback, request);
        }
        AiAfterSalesApplicationRecord application = applicationDao.findById(request.getApplicationId());
        if (application == null) {
            Asserts.fail("售后申请不存在！");
        }
        AiAfterSalesFulfillmentStatus target = AiAfterSalesFulfillmentStatus
                .fromPublicValue(request.getFulfillmentStatus());
        if (target == null) {
            Asserts.fail("履约状态不合法！");
        }
        if (!AiAfterSalesApplicationStatus.ACCEPTED.getDatabaseValue().equals(application.getStatus())
                && !AiAfterSalesApplicationStatus.COMPLETED.getDatabaseValue().equals(application.getStatus())) {
            Asserts.fail("当前售后申请不能接收履约回调！");
        }
        if (AiAfterSalesApplicationStatus.COMPLETED.getDatabaseValue().equals(application.getStatus())
                && target != AiAfterSalesFulfillmentStatus.SUCCEEDED) {
            Asserts.fail("已完成申请不能回退履约状态！");
        }
        AiAfterSalesFulfillmentCallbackRecord callback = new AiAfterSalesFulfillmentCallbackRecord();
        callback.setCallbackEventId(request.getCallbackEventId().trim());
        callback.setApplicationId(application.getId());
        callback.setFulfillmentStatus(target.getDatabaseValue());
        callback.setSource(normalizeCallbackSource(request.getSource()));
        callback.setNote(normalizeOptionalNote(request.getNote()));
        if (fulfillmentCallbackDao.insertIgnore(callback) != 1) {
            AiAfterSalesFulfillmentCallbackRecord concurrent = fulfillmentCallbackDao
                    .findByCallbackEventId(callback.getCallbackEventId());
            if (concurrent != null) {
                return replayFulfillmentCallback(concurrent, request);
            }
            Asserts.fail("履约回调正在处理中，请稍后查询！");
        }
        String applicationStatus = target == AiAfterSalesFulfillmentStatus.SUCCEEDED
                ? AiAfterSalesApplicationStatus.COMPLETED.getDatabaseValue()
                : AiAfterSalesApplicationStatus.ACCEPTED.getDatabaseValue();
        if (applicationDao.updateFulfillmentFromCallback(
                application.getId(), applicationStatus, target.getDatabaseValue(), callback.getNote()) != 1) {
            Asserts.fail("履约状态更新未完成，请稍后重试！");
        }
        AiAfterSalesApplicationRecord updated = applicationDao.findById(application.getId());
        if (updated == null) {
            Asserts.fail("履约回调结果无法确认！");
        }
        return AiAfterSalesApplicationSummary.from(updated);
    }

    private void validateActionRequest(
            Long applicationId,
            AiAfterSalesActionRequest request,
            String expectedAction
    ) {
        if (applicationId == null || applicationId <= 0 || request == null
                || !isValidIdempotencyKey(request.getActionId())
                || !isValidContentHash(request.getContentHash())) {
            Asserts.fail("售后操作确认参数不合法！");
        }
        if ("cancel".equals(expectedAction)
                && (!isBlank(request.getReason()) || !isBlank(request.getDescription()))) {
            Asserts.fail("取消售后申请不能携带修改内容！");
        }
        if ("modify".equals(expectedAction)
                && isBlank(request.getReason()) && isBlank(request.getDescription())) {
            Asserts.fail("请至少提供要修改的售后原因或说明！");
        }
        String expectedHash = actionFingerprint(
                expectedAction, applicationId, request.getReason(), request.getDescription());
        if (!MessageDigest.isEqual(
                expectedHash.getBytes(StandardCharsets.UTF_8),
                request.getContentHash().trim().getBytes(StandardCharsets.UTF_8)
        )) {
            Asserts.fail("售后操作确认内容不一致！");
        }
    }

    private AiAfterSalesApplicationSummary replayAction(
            AiAfterSalesActionRecord action,
            Long applicationId,
            AiAfterSalesActionRequest request,
            String expectedAction,
            Long memberId
    ) {
        if (!applicationId.equals(action.getApplicationId())
                || !expectedAction.equals(action.getActionType())
                || !request.getContentHash().trim().equals(action.getContentHash())) {
            Asserts.fail("该售后操作确认标识与原确认内容不一致！");
        }
        AiAfterSalesApplicationRecord application = applicationDao
                .findByIdAndMemberId(action.getApplicationId(), memberId);
        if (application == null) {
            Asserts.fail("售后操作结果无法确认！");
        }
        return AiAfterSalesApplicationSummary.from(application);
    }

    private void persistCompletedAction(
            Long memberId,
            Long applicationId,
            AiAfterSalesActionRequest request,
            String actionType
    ) {
        AiAfterSalesActionRecord action = new AiAfterSalesActionRecord();
        action.setMemberId(memberId);
        action.setApplicationId(applicationId);
        action.setActionId(request.getActionId().trim());
        action.setActionType(actionType);
        action.setContentHash(request.getContentHash().trim());
        action.setResultStatus("COMPLETED");
        if (actionDao.insertIgnore(action) == 1) {
            return;
        }
        AiAfterSalesActionRecord concurrent = actionDao
                .findByMemberIdAndActionId(memberId, action.getActionId());
        if (concurrent == null
                || !applicationId.equals(concurrent.getApplicationId())
                || !actionType.equals(concurrent.getActionType())
                || !action.getContentHash().equals(concurrent.getContentHash())) {
            Asserts.fail("售后操作确认正在处理中，请稍后查询结果！");
        }
    }

    private void validateFulfillmentCallback(AiAfterSalesFulfillmentCallbackRequest request) {
        if (request == null || request.getApplicationId() == null || request.getApplicationId() <= 0
                || isBlank(request.getCallbackEventId())
                || request.getCallbackEventId().trim().length() > 64
                || !request.getCallbackEventId().trim().matches("[A-Za-z0-9._:-]+")
                || AiAfterSalesFulfillmentStatus.fromPublicValue(request.getFulfillmentStatus()) == null) {
            Asserts.fail("履约回调参数不合法！");
        }
        normalizeCallbackSource(request.getSource());
        normalizeOptionalNote(request.getNote());
    }

    private AiAfterSalesApplicationSummary replayFulfillmentCallback(
            AiAfterSalesFulfillmentCallbackRecord callback,
            AiAfterSalesFulfillmentCallbackRequest request
    ) {
        AiAfterSalesFulfillmentStatus target = AiAfterSalesFulfillmentStatus
                .fromPublicValue(request.getFulfillmentStatus());
        if (!request.getApplicationId().equals(callback.getApplicationId())
                || target == null
                || !target.getDatabaseValue().equals(callback.getFulfillmentStatus())
                || !normalizeCallbackSource(request.getSource()).equals(callback.getSource())) {
            Asserts.fail("履约回调标识与原回调内容不一致！");
        }
        AiAfterSalesApplicationRecord application = applicationDao.findById(callback.getApplicationId());
        if (application == null) {
            Asserts.fail("履约回调结果无法确认！");
        }
        return AiAfterSalesApplicationSummary.from(application);
    }

    private String normalizeCallbackSource(String source) {
        String normalized = source == null ? "" : source.trim();
        if ("external_adapter".equals(normalized)
                || "demo_adapter".equals(normalized)
                || "manual_adapter".equals(normalized)) {
            return normalized;
        }
        Asserts.fail("履约回调来源不合法！");
        return "";
    }

    private String normalizeOptionalNote(String note) {
        if (note == null) return null;
        String normalized = note.trim();
        if (normalized.length() > 500) {
            Asserts.fail("履约说明不能超过500个字符！");
        }
        return normalized.isEmpty() ? null : normalized;
    }

    private AiAfterSalesApplicationType validateEligibilityRequest(
            AiAfterSalesEligibilityRequest request
    ) {
        if (request == null || isBlank(request.getOrderSn())) {
            Asserts.fail("订单编号不能为空！");
        }
        AiAfterSalesApplicationType type = AiAfterSalesApplicationType
                .fromValue(request.getApplicationType());
        if (type == null) {
            Asserts.fail("售后申请类型不合法！");
        }
        if (!type.isProductRequired() && request.getOrderItemId() != null) {
            Asserts.fail("取消退款按整笔订单处理，无需选择商品！");
        }
        return type;
    }

    private AiAfterSalesApplicationType validateApplyRequest(AiAfterSalesApplyRequest request) {
        if (request == null || isBlank(request.getOrderSn())) {
            Asserts.fail("订单编号不能为空！");
        }
        AiAfterSalesApplicationType type = AiAfterSalesApplicationType
                .fromValue(request.getApplicationType());
        if (type == null) {
            Asserts.fail("售后申请类型不合法！");
        }
        if (type.isProductRequired() && request.getOrderItemId() == null) {
            Asserts.fail("请选择要处理的订单商品！");
        }
        if (!type.isProductRequired() && request.getOrderItemId() != null) {
            Asserts.fail("取消退款按整笔订单处理，无需选择商品！");
        }
        validateNarrative(request.getReason(), request.getDescription());
        if (!isValidIdempotencyKey(request.getIdempotencyKey())) {
            Asserts.fail("售后提交标识不合法！");
        }
        return type;
    }

    private void validateNarrative(String reason, String description) {
        if (isBlank(reason)) {
            Asserts.fail("售后原因不能为空！");
        }
        if (reason.trim().length() > 100) {
            Asserts.fail("售后原因不能超过100个字符！");
        }
        if (description != null && description.trim().length() > 500) {
            Asserts.fail("补充说明不能超过500个字符！");
        }
    }

    private UmsMember requireCurrentMember() {
        UmsMember member = memberService.getCurrentMember();
        if (member == null || member.getId() == null) {
            Asserts.fail("当前用户未登录！");
        }
        return member;
    }

    private OmsOrder getCurrentMemberOrder(String orderSn, Long memberId) {
        OmsOrderExample example = new OmsOrderExample();
        example.createCriteria()
                .andOrderSnEqualTo(orderSn.trim())
                .andMemberIdEqualTo(memberId)
                .andDeleteStatusEqualTo(0);
        List<OmsOrder> orders = orderMapper.selectByExample(example);
        if (orders == null || orders.isEmpty()) {
            Asserts.fail("订单不存在或无权访问！");
        }
        return orders.get(0);
    }

    private OmsOrderItem resolveItemForEligibility(
            OmsOrder order,
            AiAfterSalesApplicationType type,
            Long orderItemId
    ) {
        if (!type.isProductRequired()) {
            return null;
        }
        if (orderItemId == null) {
            return null;
        }
        return getOrderItem(order.getId(), orderItemId);
    }

    private OmsOrderItem getOrderItem(Long orderId, Long orderItemId) {
        OmsOrderItemExample example = new OmsOrderItemExample();
        example.createCriteria().andIdEqualTo(orderItemId).andOrderIdEqualTo(orderId);
        List<OmsOrderItem> items = orderItemMapper.selectByExample(example);
        if (items == null || items.isEmpty()) {
            Asserts.fail("商品不属于当前订单！");
        }
        return items.get(0);
    }

    private AiAfterSalesEligibilitySummary assessEligibility(
            UmsMember member,
            OmsOrder order,
            OmsOrderItem item,
            AiAfterSalesApplicationType type
    ) {
        AiAfterSalesEligibilitySummary summary = baseEligibility(order, type);
        if (type.isProductRequired() && item == null) {
            summary.setEligible(false);
            summary.setRequiresProductSelection(true);
            summary.setDecision("needs_product_selection");
            summary.setMessage("请先选择要处理的订单商品。");
            return summary;
        }
        if (item != null) {
            summary.setProductName(item.getProductName());
            summary.setProductAttr(item.getProductAttr());
        } else {
            summary.setProductName("整笔订单");
        }

        Integer orderStatus = order.getStatus();
        if (type == AiAfterSalesApplicationType.CANCEL_REFUND) {
            if (Integer.valueOf(0).equals(orderStatus)) {
                return allowed(summary, "订单尚未支付，确认后将直接取消订单，无需进入退款审核。");
            }
            if (Integer.valueOf(1).equals(orderStatus)) {
                return allowed(summary, "订单尚未发货，可以提交取消退款申请，后续由人工审核处理。");
            }
            if (Integer.valueOf(2).equals(orderStatus) || Integer.valueOf(3).equals(orderStatus)) {
                return blocked(summary, "订单已进入发货或完成状态，不能提交取消退款申请；可根据实际情况选择退货退款、换货或维修申请。");
            }
            return blocked(summary, "当前订单状态不支持提交取消退款申请。");
        }

        if (Integer.valueOf(2).equals(orderStatus) || Integer.valueOf(3).equals(orderStatus)) {
            return allowed(summary, "订单状态允许提交售后申请，最终处理结果以审核和适用政策为准。");
        }
        if (Integer.valueOf(1).equals(orderStatus)) {
            return blocked(summary, "订单尚未发货，请选择取消退款申请；退货、换货和维修申请需在发货后提交。");
        }
        if (Integer.valueOf(0).equals(orderStatus)) {
            return blocked(summary, "订单尚未支付，暂不能提交该售后申请。");
        }
        return blocked(summary, "当前订单状态不支持提交该售后申请。");
    }

    private AiAfterSalesEligibilitySummary baseEligibility(
            OmsOrder order,
            AiAfterSalesApplicationType type
    ) {
        AiAfterSalesEligibilitySummary summary = new AiAfterSalesEligibilitySummary();
        summary.setOrderSn(order.getOrderSn());
        summary.setApplicationType(type.getValue());
        summary.setApplicationTypeLabel(type.getLabel());
        summary.setOrderStatus(orderStatusLabel(order.getStatus()));
        return summary;
    }

    private AiAfterSalesEligibilitySummary allowed(
            AiAfterSalesEligibilitySummary summary,
            String message
    ) {
        summary.setEligible(true);
        summary.setRequiresProductSelection(false);
        summary.setDecision("eligible_to_apply");
        summary.setMessage(message);
        return summary;
    }

    private AiAfterSalesEligibilitySummary blocked(
            AiAfterSalesEligibilitySummary summary,
            String message
    ) {
        summary.setEligible(false);
        summary.setRequiresProductSelection(false);
        summary.setDecision("not_eligible");
        summary.setMessage(message);
        return summary;
    }

    private void enqueueEvent(Long memberId, Long applicationId, String eventType) {
        AiAfterSalesOutboxEvent event = new AiAfterSalesOutboxEvent();
        event.setEventId(UUID.randomUUID().toString());
        event.setApplicationId(applicationId);
        event.setMemberId(memberId);
        event.setApplicationSource(SOURCE_UNIFIED_AFTER_SALES);
        event.setEventType(eventType);
        event.setStatus("PENDING");
        event.setAttemptCount(0);
        event.setAvailableAt(null);
        if (outboxDao.insert(event) != 1) {
            Asserts.fail("售后状态事件暂时无法记录，请勿重复提交并稍后查询售后记录！");
        }
    }

    private AiAfterSalesApplicationSummary replayExistingSubmission(
            AiAfterSalesApplicationRecord existing,
            String fingerprint
    ) {
        if (!fingerprint.equals(existing.getRequestFingerprint())) {
            Asserts.fail("该售后提交标识与原确认内容不一致！");
        }
        return AiAfterSalesApplicationSummary.from(existing);
    }

    private String requestFingerprint(
            AiAfterSalesApplyRequest request,
            AiAfterSalesApplicationType type
    ) {
        String canonical = request.getOrderSn().trim() + "\n"
                + type.getValue() + "\n"
                + (request.getOrderItemId() == null ? "" : request.getOrderItemId()) + "\n"
                + request.getReason().trim() + "\n"
                + normalizeDescription(request.getDescription());
        return sha256(canonical);
    }

    private String actionFingerprint(
            String action,
            Long applicationId,
            String reason,
            String description
    ) {
        String canonical = action + "\n"
                + applicationId + "\n"
                + (reason == null ? "" : reason.trim()) + "\n"
                + (description == null ? "" : description.trim());
        return sha256(canonical);
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(hash.length * 2);
            for (byte item : hash) {
                result.append(String.format("%02x", item));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 算法不可用", exception);
        }
    }

    private String openScopeKey(
            Long memberId,
            Long orderId,
            OmsOrderItem item,
            AiAfterSalesApplicationType type
    ) {
        return memberId + ":" + orderId + ":"
                + (item == null ? "order" : item.getId()) + ":" + type.getValue();
    }

    private String orderStatusLabel(Integer status) {
        if (status == null) {
            return "状态待确认";
        }
        switch (status) {
            case 0: return "待付款";
            case 1: return "待发货";
            case 2: return "已发货";
            case 3: return "已完成";
            case 4: return "已关闭";
            case 5: return "无效订单";
            default: return "状态待确认";
        }
    }

    private boolean isValidIdempotencyKey(String value) {
        return value != null && value.matches("[a-f0-9]{32}");
    }

    private boolean isValidContentHash(String value) {
        return value != null && value.matches("[a-f0-9]{64}");
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String normalizeDescription(String description) {
        return description == null ? "" : description.trim();
    }
}
