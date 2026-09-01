package com.macro.mall.portal.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.macro.mall.common.exception.Asserts;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.dao.AiCustomerConversationDao;
import com.macro.mall.portal.domain.AiCustomerConversationDetail;
import com.macro.mall.portal.domain.AiCustomerConversationMessage;
import com.macro.mall.portal.domain.AiCustomerConversationRecord;
import com.macro.mall.portal.domain.AiCustomerConversationSummary;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptMessage;
import com.macro.mall.portal.domain.AiCustomerConversationTranscriptRequest;
import com.macro.mall.portal.service.AiCustomerConversationService;
import com.macro.mall.portal.service.UmsMemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * Java owns the member boundary. FastAPI can append only a public customer
 * response and the paired message after it has already authenticated the JWT.
 */
@Service
public class AiCustomerConversationServiceImpl implements AiCustomerConversationService {
    private static final String DEFAULT_TITLE = "新的售后咨询";
    private static final Set<String> ALLOWED_TITLES = new HashSet<>(Arrays.asList(
            DEFAULT_TITLE, "订单与物流咨询", "售后政策咨询", "退货申请", "订单问题咨询", "售后咨询"
    ));
    private static final Set<String> ALLOWED_PUBLIC_RESPONSE_FIELDS = new HashSet<>(Arrays.asList(
            "answer", "verified_facts", "return_draft", "return_proposal",
            "submitted_return_application", "pending_action", "diagnosis"
    ));
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Autowired
    private AiCustomerConversationDao conversationDao;
    @Autowired
    private UmsMemberService memberService;

    @Override
    @Transactional
    public AiCustomerConversationSummary createForCurrentMember(String conversationId) {
        UmsMember member = requireCurrentMember();
        String normalizedId = normalizeConversationId(conversationId);
        AiCustomerConversationRecord existing = conversationDao
                .findByConversationIdAndMemberId(normalizedId, member.getId());
        if (existing != null) {
            return AiCustomerConversationSummary.from(existing);
        }
        AiCustomerConversationRecord record = new AiCustomerConversationRecord();
        record.setConversationId(normalizedId);
        record.setMemberId(member.getId());
        record.setTitle(DEFAULT_TITLE);
        conversationDao.insertIgnore(record);
        AiCustomerConversationRecord created = conversationDao
                .findByConversationIdAndMemberId(normalizedId, member.getId());
        if (created == null) {
            Asserts.fail("会话暂时无法创建，请稍后重试。");
        }
        return AiCustomerConversationSummary.from(created);
    }

    @Override
    public List<AiCustomerConversationSummary> listForCurrentMember() {
        UmsMember member = requireCurrentMember();
        List<AiCustomerConversationSummary> summaries = new ArrayList<>();
        for (AiCustomerConversationRecord record : conversationDao.listByMemberId(member.getId())) {
            summaries.add(AiCustomerConversationSummary.from(record));
        }
        return summaries;
    }

    @Override
    public AiCustomerConversationDetail getForCurrentMember(String conversationId) {
        UmsMember member = requireCurrentMember();
        AiCustomerConversationRecord record = requireOwnedConversation(conversationId, member.getId());
        AiCustomerConversationDetail detail = new AiCustomerConversationDetail();
        detail.setConversation(AiCustomerConversationSummary.from(record));
        detail.setMessages(conversationDao.listMessagesByConversationId(record.getConversationId()));
        return detail;
    }

    @Override
    @Transactional
    public void appendTranscriptForCurrentMember(
            String conversationId,
            AiCustomerConversationTranscriptRequest request
    ) {
        UmsMember member = requireCurrentMember();
        AiCustomerConversationRecord record = requireOwnedConversation(conversationId, member.getId());
        validateTranscript(request);
        int sequence = conversationDao.nextSequenceNo(record.getConversationId());
        for (AiCustomerConversationTranscriptMessage transcriptMessage : request.getMessages()) {
            AiCustomerConversationMessage message = new AiCustomerConversationMessage();
            message.setMessageId(UUID.randomUUID().toString());
            message.setConversationId(record.getConversationId());
            message.setSequenceNo(sequence++);
            message.setRole(transcriptMessage.getRole().trim());
            message.setContent(transcriptMessage.getContent().trim());
            message.setPublicResponseJson(emptyToNull(transcriptMessage.getPublicResponseJson()));
            if (conversationDao.insertIgnoreMessage(message) != 1) {
                Asserts.fail("会话记录暂时无法保存，请稍后重试。");
            }
        }
        conversationDao.updateTitleIfDefault(
                record.getConversationId(), member.getId(), request.getTitle().trim(), DEFAULT_TITLE
        );
        conversationDao.touch(record.getConversationId(), member.getId());
    }

    @Override
    @Transactional
    public void deleteForCurrentMember(String conversationId) {
        UmsMember member = requireCurrentMember();
        AiCustomerConversationRecord record = requireOwnedConversation(conversationId, member.getId());
        conversationDao.deleteMessagesByConversationId(record.getConversationId());
        if (conversationDao.deleteByConversationIdAndMemberId(record.getConversationId(), member.getId()) != 1) {
            Asserts.fail("会话暂时无法删除，请稍后重试。");
        }
    }

    private UmsMember requireCurrentMember() {
        UmsMember member = memberService.getCurrentMember();
        if (member == null || member.getId() == null) {
            Asserts.fail("当前用户未登录！");
        }
        return member;
    }

    private AiCustomerConversationRecord requireOwnedConversation(String conversationId, Long memberId) {
        String normalizedId = normalizeConversationId(conversationId);
        AiCustomerConversationRecord record = conversationDao
                .findByConversationIdAndMemberId(normalizedId, memberId);
        if (record == null) {
            // Do not distinguish a missing UUID from somebody else's UUID.
            // The HTTP boundary returns the same owner-safe 404 in both cases.
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "会话不存在或无权访问！");
        }
        return record;
    }

    private void validateTranscript(AiCustomerConversationTranscriptRequest request) {
        if (request == null || !ALLOWED_TITLES.contains(trim(request.getTitle()))) {
            Asserts.fail("会话标题不合法！");
        }
        List<AiCustomerConversationTranscriptMessage> messages = request.getMessages();
        if (messages == null || messages.size() != 2) {
            Asserts.fail("会话记录格式不合法！");
        }
        AiCustomerConversationTranscriptMessage user = messages.get(0);
        AiCustomerConversationTranscriptMessage assistant = messages.get(1);
        if (!"user".equals(trim(user.getRole())) || !"assistant".equals(trim(assistant.getRole()))) {
            Asserts.fail("会话记录角色不合法！");
        }
        validateContent(user.getContent());
        validateContent(assistant.getContent());
        String publicResponse = trim(assistant.getPublicResponseJson());
        if (publicResponse.isEmpty() || publicResponse.length() > 30000) {
            Asserts.fail("会话响应内容不合法！");
        }
        validatePublicResponseJson(publicResponse);
        if (user.getPublicResponseJson() != null && !user.getPublicResponseJson().trim().isEmpty()) {
            Asserts.fail("用户消息不允许附带响应内容！");
        }
    }

    private void validateContent(String content) {
        if (content == null || content.trim().isEmpty() || content.trim().length() > 8000) {
            Asserts.fail("会话消息内容不合法！");
        }
    }

    private void validatePublicResponseJson(String publicResponse) {
        try {
            JsonNode root = objectMapper.readTree(publicResponse);
            if (root == null || !root.isObject()) {
                Asserts.fail("会话响应格式不合法！");
            }
            Iterator<String> fields = root.fieldNames();
            while (fields.hasNext()) {
                if (!ALLOWED_PUBLIC_RESPONSE_FIELDS.contains(fields.next())) {
                    Asserts.fail("会话响应格式不合法！");
                }
            }
            if (!root.has("answer") || !root.get("answer").isTextual()) {
                Asserts.fail("会话响应格式不合法！");
            }
        } catch (Exception exception) {
            Asserts.fail("会话响应格式不合法！");
        }
    }

    private String normalizeConversationId(String conversationId) {
        try {
            return UUID.fromString(trim(conversationId)).toString();
        } catch (IllegalArgumentException exception) {
            Asserts.fail("会话标识不合法！");
            return "";
        }
    }

    private String trim(String value) {
        return value == null ? "" : value.trim();
    }

    private String emptyToNull(String value) {
        return value == null || value.trim().isEmpty() ? null : value;
    }
}
