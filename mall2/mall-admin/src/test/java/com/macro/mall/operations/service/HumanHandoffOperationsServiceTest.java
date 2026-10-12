package com.macro.mall.operations.service;
import com.macro.mall.operations.dao.HumanHandoffOperationsDao;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class HumanHandoffOperationsServiceTest {
 @InjectMocks HumanHandoffOperationsService service; @Mock HumanHandoffOperationsDao dao;
 @Mock com.macro.mall.operations.dao.HandoffSemanticDao semantic;
 @Mock com.macro.mall.operations.dao.HandoffSummaryDao summaries;
 @Test void filtersSharedByPageTotalsAndReasons(){service.list(7,2,20,"policy","customer_requested","unspecified");ArgumentCaptor<Map<String,Object>> q=ArgumentCaptor.forClass(Map.class);verify(dao).page(q.capture());verify(dao).totals(q.getValue());verify(dao).reasons(q.getValue());assertThat(q.getValue().get("offset")).isEqualTo(20);}
 @Test void reviewRequiresAssignedOwner(){Map<String,Object> c=new HashMap<>();c.put("assignee","another");when(dao.caseOwner("ref")).thenReturn(c);when(dao.processorRef("actor")).thenReturn("actor");assertThatThrownBy(()->service.review("ref","unspecified",0,"actor")).hasMessageContaining("403");verify(dao,never()).review(any(),any(),anyInt(),any());}
 @Test void closeCannotSkipVerification(){Map<String,Object> c=new HashMap<>();c.put("state","VERIFYING");when(dao.improvement("ref")).thenReturn(c);assertThatThrownBy(()->service.updateImprovement("ref","CLOSED",4,"not_verified","actor")).hasMessageContaining("400");verify(dao,never()).updateImprovement(any());}
 @Test void staleAnalysisLeaseCannotOverwrite(){when(dao.finish("ref","lease","SUCCEEDED","unspecified")).thenReturn(0);assertThatThrownBy(()->service.finish("ref","lease","SUCCEEDED","unspecified")).hasMessageContaining("409");verify(dao,never()).audit(any(),any(),anyInt(),any(),any());}
 @Test void retentionDefaultsToNonMutatingPreview(){when(dao.retentionCount(90)).thenReturn(2);assertThat(service.retention(true,90).get("eligible")).isEqualTo(2);verify(dao,never()).clearOneProjection(anyString());verify(dao,never()).removeEvent(anyString());}
 @Test void windowUsesUtcLiteralsRegardlessOfJvmTimezone(){
  TimeZone previous=TimeZone.getDefault();
  try{TimeZone.setDefault(TimeZone.getTimeZone("Asia/Shanghai"));service.list(7,1,20,null,null,null);
   ArgumentCaptor<Map<String,Object>> capture=ArgumentCaptor.forClass(Map.class);verify(dao).page(capture.capture());Map<String,Object> q=capture.getValue();
   java.time.format.DateTimeFormatter utc=java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(java.time.ZoneOffset.UTC);
   assertThat(q.get("endSql")).isEqualTo(utc.format(((Date)q.get("end")).toInstant()));
   assertThat(((Date)q.get("end")).getTime()-((Date)q.get("start")).getTime()).isEqualTo(7*86400000L);
  }finally{TimeZone.setDefault(previous);}
 }
 @Test void retentionOnlyClearsLockedCandidatesAndAudits(){
  when(dao.retentionCandidates(90)).thenReturn(Arrays.asList("closed-not-held"));when(dao.expiredEvents(365)).thenReturn(Arrays.asList("expired-event"));
  when(dao.clearOneProjection("closed-not-held")).thenReturn(1);when(dao.removeEvent("expired-event")).thenReturn(1);
  assertThat(service.retention(false,90,365,"operator").get("projectionsCleared")).isEqualTo(1);
  verify(dao).clearContext("closed-not-held");verify(dao).retentionAudit(anyString(),eq("operator"),eq(90),eq(365),eq(1),eq(1));
 }
 @Test void unassignedClosedCaseIsNotInProcessorQueue(){Map<String,Object> record=new HashMap<>();record.put("state","CLOSED");when(dao.caseOwner("ref")).thenReturn(record);assertThatThrownBy(()->service.processorDetail("ref","actor")).hasMessageContaining("403");}
}
