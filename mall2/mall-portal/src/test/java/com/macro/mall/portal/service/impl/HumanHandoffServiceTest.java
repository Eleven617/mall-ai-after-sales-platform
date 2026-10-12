package com.macro.mall.portal.service.impl;
import com.macro.mall.portal.dao.*;
import com.macro.mall.portal.domain.*;
import com.macro.mall.portal.service.*;
import com.macro.mall.model.UmsMember;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class HumanHandoffServiceTest {
 @InjectMocks HumanHandoffService service;
 @Mock HumanHandoffDao dao; @Mock AiCaseHandoffService legacy;
 @Mock UmsMemberService members; @Mock AiServiceCaseDao cases;
 HumanHandoffRequest request(){HumanHandoffRequest r=new HumanHandoffRequest();r.requestRef=String.join("",Collections.nCopies(64,"a"));r.scopeKey=String.join("",Collections.nCopies(64,"b"));r.contentHash=String.join("",Collections.nCopies(64,"c"));r.triggerSource="customer_requested";r.entryChannel="button";r.businessTopic="policy";r.customerReason="unspecified";r.stage="created";return r;}
 void identity(){UmsMember m=new UmsMember();m.setId(7L);when(members.getCurrentMember()).thenReturn(m);lenient().when(dao.byRequest(anyLong(),anyString())).thenReturn(null);lenient().when(dao.reused(anyLong(),anyString())).thenReturn(null);}
 @Test void repeatReturnsSameCaseWithoutWrite(){identity();HumanHandoffRequest r=request();Map<String,Object> prior=new HashMap<>();prior.put("caseRef","safe-ref");prior.put("contentHash",r.contentHash);when(dao.byRequest(7L,r.requestRef)).thenReturn(prior);assertThat(service.create(r).get("caseRef")).isEqualTo("safe-ref");verifyNoInteractions(legacy,cases);}
 @Test void changedPayloadSameKeyRejected(){identity();HumanHandoffRequest r=request();Map<String,Object> prior=new HashMap<>();prior.put("contentHash","other");when(dao.byRequest(7L,r.requestRef)).thenReturn(prior);assertThatThrownBy(()->service.create(r)).hasMessageContaining("409");verifyNoInteractions(legacy,cases);}
 @Test void activeScopeIsReusedAcrossDifferentRequests(){identity();HumanHandoffRequest r=request();when(dao.lockScope(7L,r.scopeKey)).thenReturn("active");Map<String,Object> active=new HashMap<>();active.put("state","CLAIMED");when(dao.caseState(7L,"active")).thenReturn(active);service.create(r);verify(dao).bindRequest(7L,r.requestRef,r.contentHash,"active");verifyNoInteractions(legacy,cases);}
 @Test void closedEnumsRejectUnknownCause(){HumanHandoffRequest r=request();r.customerReason="redis_lost_data";assertThatThrownBy(()->service.create(r)).hasMessageContaining("400");verifyNoInteractions(legacy,cases);}
 @Test void arbitraryCustomerTextCannotEnterProjection(){HumanHandoffRequest r=request();r.problemProjection=new HashMap<>();r.problemProjection.put("customer_statement","private raw text");assertThatThrownBy(()->service.create(r)).hasMessageContaining("400");verifyNoInteractions(legacy,cases);}
}
