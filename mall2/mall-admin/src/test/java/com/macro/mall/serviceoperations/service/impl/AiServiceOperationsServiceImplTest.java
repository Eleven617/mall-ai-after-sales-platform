package com.macro.mall.serviceoperations.service.impl;

import com.macro.mall.serviceoperations.dao.AiServiceOperationsDao;
import com.macro.mall.serviceoperations.domain.AiServiceCaseActionRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseClaimRequest;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorRecord;
import com.macro.mall.serviceoperations.domain.AiServiceCaseProcessorView;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiServiceOperationsServiceImplTest {
    @InjectMocks
    private AiServiceOperationsServiceImpl service;
    @Mock
    private AiServiceOperationsDao serviceOperationsDao;

    @Test
    void shouldClaimQueuedCaseWithAuditAndOpaqueOutboxEvent() {
        AiServiceCaseProcessorRecord queued = record("QUEUED", 1, null);
        AiServiceCaseProcessorRecord claimed = record("CLAIMED", 2, "processor-a");
        when(serviceOperationsDao.findActionIdempotent(queued.getCaseId(), "processor", "processor-a", key()))
                .thenReturn(null);
        when(serviceOperationsDao.findByCaseId(queued.getCaseId())).thenReturn(queued, claimed);
        when(serviceOperationsDao.claimIfVersion(
                queued.getCaseId(), "processor-a", 1, "人工处理人员已领取，正在核验。", "人工已开始处理该事项。"
        )).thenReturn(1);
        when(serviceOperationsDao.insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        when(serviceOperationsDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);

        AiServiceCaseProcessorView view = service.claim(queued.getCaseId(), claimRequest(1), "processor-a", repeat('a', 16));

        assertThat(view.getAssignedToMe()).isTrue();
        assertThat(view.getState()).isEqualTo("CLAIMED");
        assertThat(java.util.Arrays.stream(AiServiceCaseProcessorView.class.getDeclaredFields())
                .map(java.lang.reflect.Field::getName))
                .doesNotContain("memberId", "caseKey", "internalNote", "trace", "orderSn");
        ArgumentCaptor<String> eventType = ArgumentCaptor.forClass(String.class);
        verify(serviceOperationsDao).insertOutbox(any(), eq(queued.getCaseId()), eq(7L), eventType.capture(), eq(2), any());
        assertThat(eventType.getValue()).isEqualTo("service_case_claim");
    }

    @Test
    void shouldRequireClaimOwnershipBeforeProcessorCanResolve() {
        AiServiceCaseProcessorRecord otherAssignee = record("IN_REVIEW", 3, "processor-b");
        when(serviceOperationsDao.findActionIdempotent(otherAssignee.getCaseId(), "processor", "processor-a", key()))
                .thenReturn(null);
        when(serviceOperationsDao.findByCaseId(otherAssignee.getCaseId())).thenReturn(otherAssignee);

        assertThatThrownBy(() -> service.act(otherAssignee.getCaseId(), resolveRequest(3), "processor-a", null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("案件不存在或不属于当前处理人员");
        verify(serviceOperationsDao, never()).transitionAssignedIfVersion(any(), any(), any(), any(), any(), any(), any(), any());
        verify(serviceOperationsDao, never()).insertOutbox(any(), any(), any(), any(), any(), any());
    }

    @Test
    void shouldMoveOnlyAssignedInReviewCaseToResolvedAndKeepInternalNoteOutOfPublicView() {
        AiServiceCaseProcessorRecord reviewing = record("IN_REVIEW", 3, "processor-a");
        AiServiceCaseProcessorRecord resolved = record("RESOLVED", 4, "processor-a");
        when(serviceOperationsDao.findActionIdempotent(reviewing.getCaseId(), "processor", "processor-a", key()))
                .thenReturn(null);
        when(serviceOperationsDao.findByCaseId(reviewing.getCaseId())).thenReturn(reviewing, resolved);
        when(serviceOperationsDao.transitionAssignedIfVersion(
                eq(reviewing.getCaseId()), eq("processor-a"), eq(3), eq("IN_REVIEW"), eq("RESOLVED"), any(), any(), any()
        )).thenReturn(1);
        when(serviceOperationsDao.insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        when(serviceOperationsDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);

        AiServiceCaseProcessorView view = service.act(reviewing.getCaseId(), resolveRequest(3), "processor-a", null);

        assertThat(view.getState()).isEqualTo("RESOLVED");
        assertThat(view.getCustomerInformation()).isNull();
        ArgumentCaptor<String> note = ArgumentCaptor.forClass(String.class);
        verify(serviceOperationsDao).insertAction(
                any(), any(), any(), eq("resolve"), any(), any(), any(), note.capture(), any(), any()
        );
        assertThat(note.getValue()).isEqualTo("仅供人工审计的说明");
    }

    @Test
    void shouldRequestOneAllowListedInformationTypeWithAuditAndOutbox() {
        AiServiceCaseProcessorRecord claimed = record("CLAIMED", 2, "processor-a");
        AiServiceCaseProcessorRecord awaiting = record("AWAITING_CUSTOMER_INFORMATION", 3, "processor-a");
        awaiting.setCustomerInformationType("purchase_context");
        when(serviceOperationsDao.findActionIdempotent(claimed.getCaseId(), "processor", "processor-a", key()))
                .thenReturn(null);
        when(serviceOperationsDao.findByCaseId(claimed.getCaseId())).thenReturn(claimed, awaiting);
        when(serviceOperationsDao.transitionAssignedIfVersion(
                eq(claimed.getCaseId()), eq("processor-a"), eq(2), eq("CLAIMED"),
                eq("AWAITING_CUSTOMER_INFORMATION"), eq("purchase_context"), any(), any()
        )).thenReturn(1);
        when(serviceOperationsDao.insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        when(serviceOperationsDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);
        AiServiceCaseActionRequest request = new AiServiceCaseActionRequest();
        request.setExpectedVersion(2);
        request.setIdempotencyKey(key());
        request.setAction("request_information");
        request.setInformationType("purchase_context");
        request.setPublicMessage("请补充购买或首次使用的背景信息。 ");

        AiServiceCaseProcessorView view = service.act(claimed.getCaseId(), request, "processor-a", repeat('a', 16));

        assertThat(view.getState()).isEqualTo("AWAITING_CUSTOMER_INFORMATION");
        assertThat(view.getCustomerInformationType()).isEqualTo("purchase_context");
        ArgumentCaptor<String> eventType = ArgumentCaptor.forClass(String.class);
        verify(serviceOperationsDao).insertOutbox(any(), eq(claimed.getCaseId()), eq(7L), eventType.capture(), eq(3), any());
        assertThat(eventType.getValue()).isEqualTo("service_case_request_information");
    }

    @Test
    void shouldRejectSensitivePublicMessageBeforeAnyStateOrOutboxMutation() {
        AiServiceCaseProcessorRecord reviewing = record("IN_REVIEW", 3, "processor-a");
        when(serviceOperationsDao.findActionIdempotent(reviewing.getCaseId(), "processor", "processor-a", key()))
                .thenReturn(null);
        when(serviceOperationsDao.findByCaseId(reviewing.getCaseId())).thenReturn(reviewing);
        AiServiceCaseActionRequest request = resolveRequest(3);
        request.setPublicMessage("请联系 13800138000 继续处理。");

        assertThatThrownBy(() -> service.act(reviewing.getCaseId(), request, "processor-a", null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("不得包含联系方式");

        verify(serviceOperationsDao, never()).transitionAssignedIfVersion(any(), any(), any(), any(), any(), any(), any(), any());
        verify(serviceOperationsDao, never()).insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any());
        verify(serviceOperationsDao, never()).insertOutbox(any(), any(), any(), any(), any(), any());
    }

    private AiServiceCaseClaimRequest claimRequest(int version) {
        AiServiceCaseClaimRequest request = new AiServiceCaseClaimRequest();
        request.setExpectedVersion(version);
        request.setIdempotencyKey(key());
        return request;
    }

    private AiServiceCaseActionRequest resolveRequest(int version) {
        AiServiceCaseActionRequest request = new AiServiceCaseActionRequest();
        request.setExpectedVersion(version);
        request.setIdempotencyKey(key());
        request.setAction("resolve");
        request.setPublicMessage("已完成核验，请查看处理说明。");
        request.setInternalNote("仅供人工审计的说明");
        return request;
    }

    private AiServiceCaseProcessorRecord record(String state, int version, String assignee) {
        AiServiceCaseProcessorRecord record = new AiServiceCaseProcessorRecord();
        record.setCaseId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        record.setMemberId(7L);
        record.setQueueRef("general_after_sales");
        record.setDiagnosisCategory("tool_failure");
        record.setPriority("normal");
        record.setState(state);
        record.setStateVersion(version);
        record.setAssigneeRef(assignee);
        record.setPublicStatus("处理中");
        return record;
    }

    private String key() { return repeat('a', 32); }

    private static String repeat(char character, int length) {
        StringBuilder result = new StringBuilder(length);
        for (int index = 0; index < length; index++) result.append(character);
        return result.toString();
    }
}
