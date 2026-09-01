package com.macro.mall.operations.service;

import com.macro.mall.operations.domain.AiAfterSalesReviewView;

import java.util.List;

/** Real human review of generic after-sales requests, not fulfillment emulation. */
public interface AiAfterSalesReviewService {
    List<AiAfterSalesReviewView> listForReview(String status, Integer limit);

    AiAfterSalesReviewView reviewPending(
            Long applicationId,
            String action,
            String note,
            String reviewerUsername
    );
}
