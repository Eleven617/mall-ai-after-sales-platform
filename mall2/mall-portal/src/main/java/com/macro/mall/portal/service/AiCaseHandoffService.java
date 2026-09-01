package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.AiCaseHandoffRequest;
import com.macro.mall.portal.domain.AiCaseHandoffSummary;

/** Creates only the current member's narrowly scoped human-review handoff. */
public interface AiCaseHandoffService {
    AiCaseHandoffSummary createOrGetForCurrentMember(AiCaseHandoffRequest request);
}
