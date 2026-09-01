package com.macro.mall.operations.service.impl;

import com.macro.mall.operations.dao.AiAfterSalesReviewDao;
import com.macro.mall.operations.domain.AiAfterSalesReviewRecord;
import com.macro.mall.operations.domain.AiAfterSalesReviewView;
import com.macro.mall.operations.service.AiAfterSalesReviewService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Changes only the application's review lifecycle. Accepting a request means
 * it was received for business handling; it never claims a refund, shipment,
 * warehouse receipt, or repair fulfillment was completed.
 */
@Service
public class AiAfterSalesReviewServiceImpl implements AiAfterSalesReviewService {
    private static final String PENDING_REVIEW = "PENDING_REVIEW";
    private static final String ACCEPTED = "ACCEPTED";
    private static final String REJECTED = "REJECTED";
    private static final String SOURCE_UNIFIED_AFTER_SALES = "unified_after_sales";
    private static final String EVENT_REVIEWED = "after_sales_application_reviewed";
    private static final String FULFILLMENT_EVENT_PREFIX = "after_sales_fulfillment_requested:";

    @Autowired
    private AiAfterSalesReviewDao reviewDao;

    @Override
    public List<AiAfterSalesReviewView> listForReview(String status, Integer limit) {
        String normalizedStatus = normalizeStatus(status);
        int boundedLimit = limit == null ? 20 : Math.max(1, Math.min(50, limit));
        List<AiAfterSalesReviewRecord> records = reviewDao.listForReview(normalizedStatus, boundedLimit);
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        List<AiAfterSalesReviewView> views = new ArrayList<>();
        for (AiAfterSalesReviewRecord record : records) {
            if (record != null) {
                views.add(AiAfterSalesReviewView.from(record));
            }
        }
        return views;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AiAfterSalesReviewView reviewPending(
            Long applicationId,
            String action,
            String note,
            String reviewerUsername
    ) {
        if (applicationId == null || applicationId <= 0) {
            throw new IllegalArgumentException("售后申请标识不合法");
        }
        String normalizedAction = normalizeAction(action);
        String normalizedNote = requireCustomerSafeNote(note);
        String normalizedReviewer = requireReviewer(reviewerUsername);

        AiAfterSalesReviewRecord existing = reviewDao.findById(applicationId);
        if (existing == null) {
            throw new IllegalArgumentException("售后申请不存在");
        }
        if (!PENDING_REVIEW.equals(existing.getStatus())) {
            throw new IllegalStateException("当前售后申请已不处于待审核状态");
        }

        boolean accepted = "accept".equals(normalizedAction);
        String targetStatus = accepted ? ACCEPTED : REJECTED;
        String fulfillmentStatus = accepted ? "NOT_STARTED" : "NOT_STARTED";
        String fulfillmentNote = accepted ? "申请已受理，正在创建履约任务。" : null;
        if (reviewDao.reviewPending(
                applicationId, targetStatus, normalizedNote, normalizedReviewer,
                fulfillmentStatus, fulfillmentNote
        ) != 1) {
            throw new IllegalStateException("售后申请状态已变化，请刷新后重试");
        }
        AiAfterSalesReviewRecord reviewed = reviewDao.findById(applicationId);
        if (reviewed == null || !targetStatus.equals(reviewed.getStatus())) {
            throw new IllegalStateException("售后审核结果无法确认");
        }
        String eventType = accepted
                ? FULFILLMENT_EVENT_PREFIX + fulfillmentCommandType(reviewed.getApplicationType())
                : EVENT_REVIEWED;
        if (reviewDao.insertReviewEvent(
                UUID.randomUUID().toString(),
                reviewed.getId(),
                reviewed.getMemberId(),
                SOURCE_UNIFIED_AFTER_SALES,
                eventType
        ) != 1) {
            throw new IllegalStateException("售后审核事件无法记录");
        }
        return AiAfterSalesReviewView.from(reviewed);
    }

    private String normalizeStatus(String status) {
        if (status == null || status.trim().isEmpty()) return PENDING_REVIEW;
        String normalized = status.trim();
        if ("pending_review".equals(normalized)) return PENDING_REVIEW;
        if ("accepted".equals(normalized)) return ACCEPTED;
        if ("completed".equals(normalized)) return "COMPLETED";
        if ("rejected".equals(normalized)) return REJECTED;
        if ("cancelled".equals(normalized)) return "CANCELLED";
        throw new IllegalArgumentException("售后状态筛选不合法");
    }

    private String normalizeAction(String action) {
        if (action == null) {
            throw new IllegalArgumentException("审核操作不能为空");
        }
        String normalized = action.trim().toLowerCase();
        if ("accept".equals(normalized) || "reject".equals(normalized)) {
            return normalized;
        }
        throw new IllegalArgumentException("审核操作仅支持 accept 或 reject");
    }

    private String requireCustomerSafeNote(String note) {
        if (note == null || note.trim().isEmpty()) {
            throw new IllegalArgumentException("请填写客户可见的处理说明");
        }
        String normalized = note.trim();
        if (normalized.length() > 500) {
            throw new IllegalArgumentException("处理说明不能超过500个字符");
        }
        return normalized;
    }

    private String requireReviewer(String reviewerUsername) {
        if (reviewerUsername == null || reviewerUsername.trim().isEmpty()) {
            throw new IllegalArgumentException("审核人员身份不可用");
        }
        return reviewerUsername.trim().substring(0, Math.min(64, reviewerUsername.trim().length()));
    }

    private String fulfillmentCommandType(String applicationType) {
        if ("cancel_refund".equals(applicationType)) return "payment_refund";
        if ("return_refund".equals(applicationType)) return "warehouse_receive_then_payment_refund";
        if ("exchange".equals(applicationType)) return "warehouse_receive_then_reship";
        if ("repair".equals(applicationType)) return "repair_work_order";
        throw new IllegalStateException("售后申请类型不支持履约");
    }
}
