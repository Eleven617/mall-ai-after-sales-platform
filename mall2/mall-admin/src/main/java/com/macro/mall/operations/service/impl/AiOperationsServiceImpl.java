package com.macro.mall.operations.service.impl;

import com.macro.mall.operations.dao.AiOperationsDao;
import com.macro.mall.operations.domain.AiOperationsCaseView;
import com.macro.mall.operations.domain.AiOperationsHandoffCategorySummary;
import com.macro.mall.operations.domain.AiOperationsHandoffOverview;
import com.macro.mall.operations.domain.AiOperationsMetrics;
import com.macro.mall.operations.domain.OperationsHandoffCategoryCount;
import com.macro.mall.operations.domain.OperationsMetricCount;
import com.macro.mall.operations.service.AiOperationsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.text.SimpleDateFormat;

@Service
public class AiOperationsServiceImpl implements AiOperationsService {
    private static final Set<Integer> ALLOWED_WINDOWS = new java.util.HashSet<>(Arrays.asList(7, 30));
    private static final List<String> FORMAL_DIAGNOSIS_CATEGORIES = Arrays.asList(
            "delivery_in_transit",
            "delivery_exception",
            "order_state_review",
            "facts_incomplete",
            "policy_consultation",
            "policy_insufficient",
            "tool_failure",
            "needs_order_identifier",
            "other_pending_classification"
    );

    @Autowired
    private AiOperationsDao aiOperationsDao;

    @Override
    public List<AiOperationsCaseView> listRecentCases(Integer limit) {
        int boundedLimit = limit == null ? 20 : Math.max(1, Math.min(50, limit));
        List<AiOperationsCaseView> cases = aiOperationsDao.listRecentCases(boundedLimit);
        return cases == null ? Collections.emptyList() : cases;
    }

    @Override
    public AiOperationsCaseView getCase(String caseId) {
        return aiOperationsDao.findCaseByCaseId(caseId);
    }

    @Override
    public AiOperationsMetrics getMetrics(Integer windowDays) {
        if (!ALLOWED_WINDOWS.contains(windowDays)) {
            throw new IllegalArgumentException("仅支持 7 或 30 天运营聚合窗口");
        }
        Date toTime = new Date();
        Date fromTime = startOfWindow(windowDays, toTime);
        AiOperationsMetrics metrics = new AiOperationsMetrics();
        metrics.setWindowDays(windowDays);
        metrics.setAfterSalesByStatus(toCountMap(aiOperationsDao.countAfterSalesByStatus(fromTime)));
        metrics.setReasonCounts(toCountMap(aiOperationsDao.countReasons(fromTime)));
        metrics.setOutboxByStatus(toCountMap(aiOperationsDao.countOutboxByStatus(fromTime)));
        metrics.setDeliveryByStatus(toCountMap(aiOperationsDao.countDeliveryByStatus(fromTime)));
        metrics.setHandoffOverview(buildHandoffOverview(windowDays, fromTime, toTime));
        return metrics;
    }

    private Date startOfWindow(Integer windowDays, Date toTime) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTime(toTime);
        calendar.add(Calendar.DAY_OF_YEAR, -windowDays);
        return calendar.getTime();
    }

    private AiOperationsHandoffOverview buildHandoffOverview(
            Integer windowDays,
            Date fromTime,
            Date toTime
    ) {
        long total = safeTotal(aiOperationsDao.countUniqueHandoffs(fromTime, toTime));
        Map<String, Long> counts = toHandoffCountMap(
                aiOperationsDao.countUniqueHandoffsByCategory(fromTime, toTime)
        );
        List<AiOperationsHandoffCategorySummary> categories = new java.util.ArrayList<>();
        for (String category : FORMAL_DIAGNOSIS_CATEGORIES) {
            long count = safeTotal(counts.get(category));
            AiOperationsHandoffCategorySummary summary = new AiOperationsHandoffCategorySummary();
            summary.setCategory(category);
            summary.setCount(count);
            summary.setPercentage(total == 0 ? 0D : roundPercentage(count, total));
            categories.add(summary);
        }
        AiOperationsHandoffOverview overview = new AiOperationsHandoffOverview();
        overview.setWindowDays(windowDays);
        overview.setWindowStart(formatWindowTime(fromTime));
        overview.setWindowEnd(formatWindowTime(toTime));
        overview.setTotalUniqueHandoffs(total);
        overview.setCategories(categories);
        return overview;
    }

    private Map<String, Long> toHandoffCountMap(List<OperationsHandoffCategoryCount> rows) {
        Map<String, Long> counts = new LinkedHashMap<>();
        if (rows == null) {
            return counts;
        }
        for (OperationsHandoffCategoryCount row : rows) {
            if (row == null || row.getMetricKey() == null) {
                continue;
            }
            counts.put(row.getMetricKey(), safeTotal(row.getTotal()));
        }
        return counts;
    }

    private long safeTotal(Long value) {
        return value == null || value < 0 ? 0L : value;
    }

    private double roundPercentage(long count, long total) {
        return Math.round((count * 10000D / total)) / 100D;
    }

    private String formatWindowTime(Date value) {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(value);
    }

    private Map<String, Long> toCountMap(List<OperationsMetricCount> rows) {
        Map<String, Long> counts = new LinkedHashMap<>();
        if (rows == null) {
            return counts;
        }
        for (OperationsMetricCount row : rows) {
            if (row == null || row.getMetricKey() == null || row.getTotal() == null || row.getTotal() < 0) {
                continue;
            }
            counts.put(row.getMetricKey(), row.getTotal());
        }
        return counts;
    }
}
