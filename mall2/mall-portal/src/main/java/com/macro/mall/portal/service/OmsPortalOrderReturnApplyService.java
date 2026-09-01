package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.OmsOrderReturnApplyParam;

/**
 * Native mall return-application boundary. Unified AI after-sales uses the
 * separate AI service and never keeps a second legacy AI write path here.
 */
public interface OmsPortalOrderReturnApplyService {
    int create(OmsOrderReturnApplyParam returnApply);
}
