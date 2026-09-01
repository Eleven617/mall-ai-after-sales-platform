package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.ApiException;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiCaseHandoffDao;
import com.macro.mall.portal.dao.AiServiceCaseDao;
import com.macro.mall.portal.domain.AiCaseHandoffRecord;
import com.macro.mall.portal.domain.AiCaseHandoffRequest;
import com.macro.mall.portal.domain.AiCaseHandoffSummary;
import com.macro.mall.portal.domain.AiServiceCaseRecord;
import com.macro.mall.portal.domain.AiServiceCaseRoutingRule;
import com.macro.mall.portal.service.UmsMemberService;
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
class AiCaseHandoffServiceImplTest {
    @InjectMocks
    private AiCaseHandoffServiceImpl service;
    @Mock
    private AiCaseHandoffDao handoffDao;
    @Mock
    private UmsMemberService memberService;
    @Mock
    private AiServiceCaseDao serviceCaseDao;

    @Test
    void shouldCreateMinimalHandoffScopedToCurrentMember() {
        UmsMember member = new UmsMember();
        member.setId(7L);
        AiCaseHandoffRecord created = record("case-12345678-1234-1234-1234-123456789abc");
        when(memberService.getCurrentMember()).thenReturn(member);
        when(handoffDao.findByMemberIdAndCaseKey(eq(7L), eq(key())))
                .thenReturn(null, created);
        when(handoffDao.insertIgnore(any(AiCaseHandoffRecord.class))).thenReturn(1);
        when(serviceCaseDao.findByMemberIdAndCaseKey(7L, key())).thenReturn(queuedCase());

        AiCaseHandoffSummary result = service.createOrGetForCurrentMember(request());

        ArgumentCaptor<AiCaseHandoffRecord> captor = ArgumentCaptor.forClass(AiCaseHandoffRecord.class);
        verify(handoffDao).insertIgnore(captor.capture());
        AiCaseHandoffRecord saved = captor.getValue();
        assertThat(saved.getMemberId()).isEqualTo(7L);
        assertThat(saved.getCaseKey()).isEqualTo(key());
        assertThat(saved.getSourceFlow()).isEqualTo("customer_diagnosis");
        assertThat(saved.getDiagnosisCategory()).isEqualTo("tool_failure");
        assertThat(saved.getHandoffReason()).isEqualTo("tool_failure");
        assertThat(saved.getCaseStatus()).isEqualTo("OPEN");
        assertThat(result.getCaseId()).isEqualTo(created.getCaseId());
        assertThat(java.util.Arrays.stream(AiCaseHandoffRecord.class.getDeclaredFields())
                .map(java.lang.reflect.Field::getName))
                .doesNotContain("message", "summary", "orderSn", "phone", "token");
    }

    @Test
    void shouldReuseCurrentMembersExistingCaseWithoutWritingAgain() {
        UmsMember member = new UmsMember();
        member.setId(7L);
        AiCaseHandoffRecord existing = record("case-12345678-1234-1234-1234-123456789abc");
        when(memberService.getCurrentMember()).thenReturn(member);
        when(handoffDao.findByMemberIdAndCaseKey(7L, key())).thenReturn(existing);
        when(serviceCaseDao.findByMemberIdAndCaseKey(7L, key())).thenReturn(queuedCase());

        AiCaseHandoffSummary result = service.createOrGetForCurrentMember(request());

        assertThat(result.getCaseId()).isEqualTo(existing.getCaseId());
        verify(handoffDao, never()).insertIgnore(any());
    }

    @Test
    void shouldRejectModelOrClientInventedCategoryBeforePersistence() {
        AiCaseHandoffRequest request = request();
        request.setDiagnosisCategory("refund_directly");

        assertThatThrownBy(() -> service.createOrGetForCurrentMember(request))
                .isInstanceOf(ApiException.class)
                .hasMessage("诊断分类不合法！");
        verify(handoffDao, never()).findByMemberIdAndCaseKey(any(), any());
    }

    @Test
    void shouldQueueConcurrentHandoffInsteadOfLeavingOnlyTheHandoffRecord() {
        UmsMember member = new UmsMember();
        member.setId(7L);
        AiCaseHandoffRecord concurrent = record("case-12345678-1234-1234-1234-123456789abc");
        AiServiceCaseRoutingRule rule = new AiServiceCaseRoutingRule();
        rule.setEligibleQueueRef("general_after_sales");
        rule.setPriority("normal");
        when(memberService.getCurrentMember()).thenReturn(member);
        when(handoffDao.findByMemberIdAndCaseKey(7L, key())).thenReturn(null, concurrent);
        when(handoffDao.insertIgnore(any(AiCaseHandoffRecord.class))).thenReturn(0);
        when(serviceCaseDao.findByMemberIdAndCaseKey(7L, key())).thenReturn(null);
        when(serviceCaseDao.findActiveRoutingRule("tool_failure")).thenReturn(rule);
        when(serviceCaseDao.insertIgnoreCase(any(AiServiceCaseRecord.class))).thenReturn(1);
        when(serviceCaseDao.insertOutbox(any(), any(), any(), any(), any(), any())).thenReturn(1);

        AiCaseHandoffSummary result = service.createOrGetForCurrentMember(request());

        assertThat(result.getCaseId()).isEqualTo(concurrent.getCaseId());
        verify(serviceCaseDao).insertIgnoreCase(any(AiServiceCaseRecord.class));
        verify(serviceCaseDao).insertOutbox(any(), any(), any(), eq("service_case_queued"), eq(1), any());
    }

    private AiCaseHandoffRequest request() {
        AiCaseHandoffRequest request = new AiCaseHandoffRequest();
        request.setCaseKey(key());
        request.setSourceFlow("customer_diagnosis");
        request.setDiagnosisCategory("tool_failure");
        request.setEvidenceStatus("unavailable");
        request.setHandoffReason("tool_failure");
        request.setRequiresHumanReview(true);
        request.setSchemaVersion("1");
        return request;
    }

    private AiCaseHandoffRecord record(String caseId) {
        AiCaseHandoffRecord record = new AiCaseHandoffRecord();
        record.setCaseId(caseId);
        record.setCaseKey(key());
        record.setMemberId(7L);
        record.setSourceFlow("customer_diagnosis");
        record.setDiagnosisCategory("tool_failure");
        record.setEvidenceStatus("unavailable");
        record.setHandoffReason("tool_failure");
        record.setRequiresHumanReview(true);
        record.setCaseStatus("OPEN");
        record.setSchemaVersion("1");
        return record;
    }

    private String key() {
        StringBuilder result = new StringBuilder(64);
        for (int index = 0; index < 64; index++) {
            result.append('a');
        }
        return result.toString();
    }

    private AiServiceCaseRecord queuedCase() {
        AiServiceCaseRecord record = new AiServiceCaseRecord();
        record.setCaseId("case-12345678-1234-1234-1234-123456789abc");
        record.setCaseKey(key());
        record.setState("QUEUED");
        return record;
    }
}
