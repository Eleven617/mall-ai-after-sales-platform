package com.macro.mall.serviceoperations.dao;

import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorRecord;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** Transactional DAO for the dedicated human service-case state machine. */
public interface AiServiceOperationsDao {
    List<AiServiceCaseProcessorRecord> listVisibleForProcessor(
            @Param("username") String username,
            @Param("limit") Integer limit
    );

    AiServiceCaseProcessorRecord findByCaseId(@Param("caseId") String caseId);

    Integer findActionIdempotent(
            @Param("caseId") String caseId,
            @Param("actorKind") String actorKind,
            @Param("actorRef") String actorRef,
            @Param("idempotencyKey") String idempotencyKey
    );

    int claimIfVersion(
            @Param("caseId") String caseId,
            @Param("processor") String processor,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("publicStatus") String publicStatus,
            @Param("publicMessage") String publicMessage
    );

    int transitionAssignedIfVersion(
            @Param("caseId") String caseId,
            @Param("processor") String processor,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("expectedState") String expectedState,
            @Param("targetState") String targetState,
            @Param("informationType") String informationType,
            @Param("publicStatus") String publicStatus,
            @Param("publicMessage") String publicMessage
    );

    int insertAction(
            @Param("actionId") String actionId,
            @Param("caseId") String caseId,
            @Param("actorRef") String actorRef,
            @Param("actionType") String actionType,
            @Param("expectedVersion") Integer expectedVersion,
            @Param("resultCode") String resultCode,
            @Param("publicMessage") String publicMessage,
            @Param("internalNote") String internalNote,
            @Param("idempotencyKey") String idempotencyKey,
            @Param("correlationRef") String correlationRef
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
