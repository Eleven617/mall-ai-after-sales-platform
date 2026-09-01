package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiServiceCaseRecord;
import com.macro.mall.portal.domain.AiServiceCaseRoutingRule;
import com.macro.mall.portal.domain.AiServiceCaseTimelineEntry;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** Java-owned persistence boundary for service-case state and transactional events. */
public interface AiServiceCaseDao {
    AiServiceCaseRoutingRule findActiveRoutingRule(@Param("category") String category);
    int insertIgnoreCase(AiServiceCaseRecord record);
    AiServiceCaseRecord findByMemberIdAndCaseKey(@Param("memberId") Long memberId, @Param("caseKey") String caseKey);
    AiServiceCaseRecord findByCaseIdAndMemberId(@Param("caseId") String caseId, @Param("memberId") Long memberId);
    List<AiServiceCaseRecord> listByMemberId(@Param("memberId") Long memberId);
    List<AiServiceCaseTimelineEntry> listPublicTimeline(@Param("caseId") String caseId);
    int insertAction(
            @Param("actionId") String actionId,
            @Param("caseId") String caseId,
            @Param("actorKind") String actorKind,
            @Param("actorRef") String actorRef,
            @Param("actionType") String actionType,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("resultCode") String resultCode,
            @Param("publicMessage") String publicMessage,
            @Param("idempotencyKey") String idempotencyKey,
            @Param("correlationRef") String correlationRef
    );
    Integer findActionIdempotent(
            @Param("caseId") String caseId,
            @Param("actorKind") String actorKind,
            @Param("actorRef") String actorRef,
            @Param("idempotencyKey") String idempotencyKey
    );
    int updateCustomerInformationIfVersion(
            @Param("caseId") String caseId,
            @Param("memberId") Long memberId,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("informationType") String informationType,
            @Param("information") String information,
            @Param("publicStatus") String publicStatus,
            @Param("publicMessage") String publicMessage
    );
    int cancelIfVersion(
            @Param("caseId") String caseId,
            @Param("memberId") Long memberId,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("publicStatus") String publicStatus,
            @Param("publicMessage") String publicMessage
    );
    int reopenIfVersion(
            @Param("caseId") String caseId,
            @Param("memberId") Long memberId,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("reason") String reason,
            @Param("publicStatus") String publicStatus,
            @Param("publicMessage") String publicMessage
    );
    int insertOutbox(
            @Param("eventId") String eventId,
            @Param("caseId") String caseId,
            @Param("memberId") Long memberId,
            @Param("eventType") String eventType,
            @Param("stateVersion") Integer stateVersion,
            @Param("correlationRef") String correlationRef
    );
}
