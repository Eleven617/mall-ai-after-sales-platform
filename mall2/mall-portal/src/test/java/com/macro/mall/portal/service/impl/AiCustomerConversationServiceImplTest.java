package com.macro.mall.portal.service.impl;

import com.macro.mall.common.exception.ApiException;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiCustomerConversationDao;
import com.macro.mall.portal.domain.AiCustomerConversationMessage;
import com.macro.mall.portal.domain.AiCustomerConversationRecord;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptMessage;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptRequest;
import com.macro.mall.portal.service.UmsMemberService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.server.ResponseStatusException;

import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiCustomerConversationServiceImplTest {
    private static final String CONVERSATION_ID = "11111111-1111-4111-8111-111111111111";

    @InjectMocks
    private AiCustomerConversationServiceImpl service;
    @Mock
    private AiCustomerConversationDao conversationDao;
    @Mock
    private UmsMemberService memberService;

    @Test
    void shouldCreateConversationOnlyForCurrentMemberAndUseGenericTitle() {
        when(memberService.getCurrentMember()).thenReturn(member(7L));
        when(conversationDao.findByConversationIdAndMemberId(CONVERSATION_ID, 7L))
                .thenReturn(null, record(CONVERSATION_ID, 7L));
        when(conversationDao.insertIgnore(any(AiCustomerConversationRecord.class))).thenReturn(1);

        service.createForCurrentMember(CONVERSATION_ID);

        ArgumentCaptor<AiCustomerConversationRecord> captor = ArgumentCaptor.forClass(AiCustomerConversationRecord.class);
        verify(conversationDao).insertIgnore(captor.capture());
        assertThat(captor.getValue().getMemberId()).isEqualTo(7L);
        assertThat(captor.getValue().getConversationId()).isEqualTo(CONVERSATION_ID);
        assertThat(captor.getValue().getTitle()).isEqualTo("新的售后咨询");
    }

    @Test
    void shouldRejectForeignConversationWithoutRevealingWhetherItExists() {
        when(memberService.getCurrentMember()).thenReturn(member(8L));
        when(conversationDao.findByConversationIdAndMemberId(CONVERSATION_ID, 8L)).thenReturn(null);

        assertThatThrownBy(() -> service.getForCurrentMember(CONVERSATION_ID))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("会话不存在或无权访问");
        verify(conversationDao).findByConversationIdAndMemberId(CONVERSATION_ID, 8L);
    }

    @Test
    void shouldPersistOnlyAValidatedPairedPublicTranscript() {
        when(memberService.getCurrentMember()).thenReturn(member(7L));
        when(conversationDao.findByConversationIdAndMemberId(CONVERSATION_ID, 7L))
                .thenReturn(record(CONVERSATION_ID, 7L));
        when(conversationDao.nextSequenceNo(CONVERSATION_ID)).thenReturn(1);
        when(conversationDao.insertIgnoreMessage(any(AiCustomerConversationMessage.class))).thenReturn(1);

        service.appendTranscriptForCurrentMember(CONVERSATION_ID, transcript("订单与物流咨询", publicResponse()));

        ArgumentCaptor<AiCustomerConversationMessage> captor = ArgumentCaptor.forClass(AiCustomerConversationMessage.class);
        verify(conversationDao, org.mockito.Mockito.times(2)).insertIgnoreMessage(captor.capture());
        assertThat(captor.getAllValues()).extracting(AiCustomerConversationMessage::getRole)
                .containsExactly("user", "assistant");
        assertThat(captor.getAllValues().get(1).getPublicResponseJson()).isEqualTo(publicResponse());
        verify(conversationDao).updateTitleIfDefault(CONVERSATION_ID, 7L, "订单与物流咨询", "新的售后咨询");
        verify(conversationDao).touch(CONVERSATION_ID, 7L);
    }

    @Test
    void shouldRejectInternalResponseFieldsBeforeAnyMessageIsWritten() {
        when(memberService.getCurrentMember()).thenReturn(member(7L));
        when(conversationDao.findByConversationIdAndMemberId(CONVERSATION_ID, 7L))
                .thenReturn(record(CONVERSATION_ID, 7L));

        assertThatThrownBy(() -> service.appendTranscriptForCurrentMember(
                CONVERSATION_ID,
                transcript("订单与物流咨询", "{\"answer\":\"ok\",\"rag_context\":[\"secret\"]}")
        )).isInstanceOf(ApiException.class)
                .hasMessage("会话响应格式不合法！");
        verify(conversationDao, never()).nextSequenceNo(any());
        verify(conversationDao, never()).insertIgnoreMessage(any());
    }

    @Test
    void shouldRejectClientInventedTitleBeforePersistence() {
        when(memberService.getCurrentMember()).thenReturn(member(7L));
        when(conversationDao.findByConversationIdAndMemberId(CONVERSATION_ID, 7L))
                .thenReturn(record(CONVERSATION_ID, 7L));

        assertThatThrownBy(() -> service.appendTranscriptForCurrentMember(
                CONVERSATION_ID, transcript("原始客户问题 202607240001", publicResponse())
        )).isInstanceOf(ApiException.class)
                .hasMessage("会话标题不合法！");
        verify(conversationDao, never()).nextSequenceNo(any());
    }

    private UmsMember member(Long id) {
        UmsMember member = new UmsMember();
        member.setId(id);
        return member;
    }

    private AiCustomerConversationRecord record(String conversationId, Long memberId) {
        AiCustomerConversationRecord record = new AiCustomerConversationRecord();
        record.setConversationId(conversationId);
        record.setMemberId(memberId);
        record.setTitle("新的售后咨询");
        return record;
    }

    private AiCustomerConversationTranscriptRequest transcript(String title, String publicResponse) {
        AiCustomerConversationTranscriptMessage user = new AiCustomerConversationTranscriptMessage();
        user.setRole("user");
        user.setContent("我想查询订单");
        AiCustomerConversationTranscriptMessage assistant = new AiCustomerConversationTranscriptMessage();
        assistant.setRole("assistant");
        assistant.setContent("订单查询完成。");
        assistant.setPublicResponseJson(publicResponse);
        AiCustomerConversationTranscriptRequest request = new AiCustomerConversationTranscriptRequest();
        request.setTitle(title);
        request.setMessages(Arrays.asList(user, assistant));
        return request;
    }

    private String publicResponse() {
        return "{\"answer\":\"订单查询完成。\",\"verified_facts\":[]}";
    }
}
