package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiCustomerConversationMessage;
import com.macro.mall.portal.domain.AiCustomerConversationRecord;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/** All queries remain member-scoped before history can be returned or deleted. */
public interface AiCustomerConversationDao {
    int insertIgnore(AiCustomerConversationRecord record);

    AiCustomerConversationRecord findByConversationIdAndMemberId(
            @Param("conversationId") String conversationId,
            @Param("memberId") Long memberId
    );

    List<AiCustomerConversationRecord> listByMemberId(@Param("memberId") Long memberId);

    int nextSequenceNo(@Param("conversationId") String conversationId);

    int insertIgnoreMessage(AiCustomerConversationMessage message);

    List<AiCustomerConversationMessage> listMessagesByConversationId(
            @Param("conversationId") String conversationId
    );

    int updateTitleIfDefault(
            @Param("conversationId") String conversationId,
            @Param("memberId") Long memberId,
            @Param("title") String title,
            @Param("defaultTitle") String defaultTitle
    );

    int touch(@Param("conversationId") String conversationId, @Param("memberId") Long memberId);

    int deleteMessagesByConversationId(@Param("conversationId") String conversationId);

    int deleteByConversationIdAndMemberId(
            @Param("conversationId") String conversationId,
            @Param("memberId") Long memberId
    );
}
