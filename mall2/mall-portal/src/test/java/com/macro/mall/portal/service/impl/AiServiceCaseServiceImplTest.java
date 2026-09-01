package com.macro.mall.portal.service.impl;

import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiServiceCaseDao;
import com.macro.mall.portal.domain.AiServiceCaseCustomerInformationRequest;
import com.macro.mall.portal.domain.AiServiceCasePublicView;
import com.macro.mall.portal.domain.AiServiceCaseRecord;
import com.macro.mall.portal.domain.AiServiceCaseReopenRequest;
import com.macro.mall.portal.service.UmsMemberService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Arrays;
import java.util.Date;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
class AiServiceCaseServiceImplTest {
    @InjectMocks
    private AiServiceCaseServiceImpl service;
    @Mock
    private AiServiceCaseDao serviceCaseDao;
    @Mock
    private UmsMemberService memberService;

    @Test
    void shouldProjectOnlyCustomerSafeCaseFieldsAndCapabilities() {
        when(memberService.getCurrentMember()).thenReturn(member());
        AiServiceCaseRecord queued = record("QUEUED", 1);
        queued.setQueueRef("general_after_sales");
        queued.setAssigneeRef("processor-a");
        queued.setCaseKey("a" + repeat('b', 63));
        when(serviceCaseDao.listByMemberId(7L)).thenReturn(Arrays.asList(queued));

        List<AiServiceCasePublicView> result = service.listMine();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getCanCancel()).isTrue();
        assertThat(result.get(0).getCanReopen()).isFalse();
        assertThat(result.get(0).getCustomerInformationRequired()).isFalse();
        assertThat(Arrays.stream(AiServiceCasePublicView.class.getDeclaredFields())
                .map(java.lang.reflect.Field::getName))
                .doesNotContain("memberId", "queueRef", "assigneeRef", "caseKey", "internalNote", "trace");
    }

    @Test
    void shouldReopenResolvedCaseWithVersionIdempotencyAuditAndOutbox() {
        AiServiceCaseRecord resolved = record("RESOLVED", 3);
        AiServiceCaseRecord reopened = record("REOPENED", 4);
        when(memberService.getCurrentMember()).thenReturn(member());
        when(serviceCaseDao.findByCaseIdAndMemberId(resolved.getCaseId(), 7L))
                .thenReturn(resolved, reopened);
        when(serviceCaseDao.findActionIdempotent(eq(resolved.getCaseId()), eq("customer"), eq("7"), any()))
                .thenReturn(null);
        when(serviceCaseDao.reopenIfVersion(
                eq(resolved.getCaseId()), eq(7L), eq(3), eq("问题仍未解决"), any(), any()
        )).thenReturn(1);
        when(serviceCaseDao.insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        when(serviceCaseDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);
        AiServiceCaseReopenRequest request = new AiServiceCaseReopenRequest();
        request.setExpectedVersion(3);
        request.setIdempotencyKey(repeat('a', 32));
        request.setReason("问题仍未解决");

        AiServiceCasePublicView result = service.reopenMine(resolved.getCaseId(), request, repeat('a', 16));

        assertThat(result.getState()).isEqualTo("REOPENED");
        ArgumentCaptor<String> eventType = ArgumentCaptor.forClass(String.class);
        verify(serviceCaseDao).insertOutbox(any(), eq(resolved.getCaseId()), eq(7L), eventType.capture(), eq(4), any());
        assertThat(eventType.getValue()).isEqualTo("service_case_customer_reopen");
    }

    @Test
    void shouldUseOnlyTheRequestedSupplementTypeAndWriteAuditOutboxAfterStateChange() {
        AiServiceCaseRecord awaiting = record("AWAITING_CUSTOMER_INFORMATION", 2);
        awaiting.setCustomerInformationType("purchase_context");
        AiServiceCaseRecord reviewing = record("IN_REVIEW", 3);
        reviewing.setCustomerInformationType("purchase_context");
        when(memberService.getCurrentMember()).thenReturn(member());
        when(serviceCaseDao.findByCaseIdAndMemberId(awaiting.getCaseId(), 7L))
                .thenReturn(awaiting, reviewing);
        when(serviceCaseDao.findActionIdempotent(eq(awaiting.getCaseId()), eq("customer"), eq("7"), any()))
                .thenReturn(null);
        when(serviceCaseDao.updateCustomerInformationIfVersion(
                eq(awaiting.getCaseId()), eq(7L), eq(2), eq("purchase_context"),
                eq("签收后首次使用时出现问题"), any(), any()
        )).thenReturn(1);
        when(serviceCaseDao.insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(1);
        when(serviceCaseDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);
        AiServiceCaseCustomerInformationRequest request = new AiServiceCaseCustomerInformationRequest();
        request.setExpectedVersion(2);
        request.setIdempotencyKey(repeat('a', 32));
        request.setInformationType("purchase_context");
        request.setInformation("签收后首次使用时出现问题");

        AiServiceCasePublicView result = service.submitCustomerInformation(
                awaiting.getCaseId(), request, repeat('a', 16)
        );

        assertThat(result.getState()).isEqualTo("IN_REVIEW");
        verify(serviceCaseDao).updateCustomerInformationIfVersion(
                eq(awaiting.getCaseId()), eq(7L), eq(2), eq("purchase_context"),
                eq("签收后首次使用时出现问题"), any(), any()
        );
        ArgumentCaptor<String> eventType = ArgumentCaptor.forClass(String.class);
        verify(serviceCaseDao).insertOutbox(any(), eq(awaiting.getCaseId()), eq(7L), eventType.capture(), eq(3), any());
        assertThat(eventType.getValue()).isEqualTo("service_case_customer_information");
    }

    @Test
    void shouldNotCreateAuditOrOutboxWhenSupplementTypeOrVersionIsRejectedByStateUpdate() {
        AiServiceCaseRecord awaiting = record("AWAITING_CUSTOMER_INFORMATION", 2);
        awaiting.setCustomerInformationType("purchase_context");
        when(memberService.getCurrentMember()).thenReturn(member());
        when(serviceCaseDao.findByCaseIdAndMemberId(awaiting.getCaseId(), 7L)).thenReturn(awaiting);
        when(serviceCaseDao.findActionIdempotent(eq(awaiting.getCaseId()), eq("customer"), eq("7"), any()))
                .thenReturn(null);
        // The SQL predicate also checks customer_information_type and expected version.
        when(serviceCaseDao.updateCustomerInformationIfVersion(
                eq(awaiting.getCaseId()), eq(7L), eq(2), eq("problem_description"), any(), any(), any()
        )).thenReturn(0);
        AiServiceCaseCustomerInformationRequest request = new AiServiceCaseCustomerInformationRequest();
        request.setExpectedVersion(2);
        request.setIdempotencyKey(repeat('a', 32));
        request.setInformationType("problem_description");
        request.setInformation("不能使用与人工要求不同的补件类型");

        org.assertj.core.api.Assertions.assertThatThrownBy(
                () -> service.submitCustomerInformation(awaiting.getCaseId(), request, repeat('a', 16))
        ).isInstanceOf(IllegalStateException.class);

        verify(serviceCaseDao, never()).insertAction(any(), any(), any(), any(), any(), any(), any(), any(), any(), any());
        verify(serviceCaseDao, never()).insertOutbox(any(), any(), any(), any(), any(), any());
    }

    private UmsMember member() {
        UmsMember member = new UmsMember();
        member.setId(7L);
        return member;
    }

    private AiServiceCaseRecord record(String state, int version) {
        AiServiceCaseRecord record = new AiServiceCaseRecord();
        record.setCaseId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        record.setMemberId(7L);
        record.setDiagnosisCategory("tool_failure");
        record.setState(state);
        record.setStateVersion(version);
        record.setPublicStatus("处理中");
        record.setLastPublicMessage("处理说明");
        record.setUpdatedAt(new Date());
        return record;
    }

    private static String repeat(char character, int length) {
        StringBuilder result = new StringBuilder(length);
        for (int index = 0; index < length; index++) result.append(character);
        return result.toString();
    }
}
