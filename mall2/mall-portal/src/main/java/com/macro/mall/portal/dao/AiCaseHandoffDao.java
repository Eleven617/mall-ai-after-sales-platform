package com.macro.mall.portal.dao;

import com.macro.mall.portal.domain.AiCaseHandoffRecord;
import org.apache.ibatis.annotations.Param;

/** Member-scoped de-duplication boundary for a privacy-minimal case handoff. */
public interface AiCaseHandoffDao {
    AiCaseHandoffRecord findByMemberIdAndCaseKey(
            @Param("memberId") Long memberId,
            @Param("caseKey") String caseKey
    );

    int insertIgnore(AiCaseHandoffRecord record);
}
