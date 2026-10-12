package com.macro.mall.operations.service;
import com.macro.mall.operations.dao.HandoffSemanticDao;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class HandoffSemanticServiceTest {
 @InjectMocks HandoffSemanticService service; @Mock HandoffSemanticDao dao;
 String ref="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
 @BeforeEach void sqlMissingRows(){lenient().when(dao.request(anyString())).thenReturn(null);lenient().when(dao.problem(anyString())).thenReturn(null);}
 Map<String,Object> problem(){Map<String,Object> p=new HashMap<>();p.put("caseRef",ref);p.put("version",1);p.put("topic","exchange");p.put("quality","READY");p.put("projection","{}");return p;}
 @Test void deletedProjectionIsNeverReturned(){assertThatThrownBy(()->service.problem(ref)).hasMessageContaining("404");}
 @Test void tooLargeSearchDoesNotSilentlyTruncate(){when(dao.problem(ref)).thenReturn(problem());when(dao.candidates(30,"exchange")).thenReturn(Collections.nCopies(5001,problem()));assertThatThrownBy(()->service.candidates(ref,30,false)).hasMessageContaining("narrow_search_scope");}
 @Test void sameTopicFilterIsDefault(){when(dao.problem(ref)).thenReturn(problem());when(dao.candidates(7,"exchange")).thenReturn(new ArrayList<>());service.candidates(ref,7,false);verify(dao).candidates(7,"exchange");}
 @Test void expiredLeaseCannotMarkReady(){Map<String,Object> q=new HashMap<>();q.put("state","READY");q.put("model","BAAI/bge-small-zh-v1.5");assertThatThrownBy(()->service.finish(q)).hasMessageContaining("409");}
 @Test void staleGroupVersionDoesNotWriteMember(){Map<String,Object> g=new HashMap<>();g.put("version",2);when(dao.group(ref)).thenReturn(g);when(dao.members(ref)).thenReturn(new ArrayList<>());Map<String,Object> q=new HashMap<>();q.put("requestRef",UUID.randomUUID().toString());q.put("action","add");q.put("version",1);assertThatThrownBy(()->service.membership(ref,q,"ops")).hasMessageContaining("409");verify(dao,never()).add(any());}
 @Test void oneMemberCannotTriggerAnalysis(){Map<String,Object> g=new HashMap<>();g.put("version",1);when(dao.group(ref)).thenReturn(g);when(dao.members(ref)).thenReturn(new ArrayList<>());Map<String,Object> q=new HashMap<>();q.put("requestRef",UUID.randomUUID().toString());q.put("version",1);assertThatThrownBy(()->service.requestAnalysis(ref,q,"ops")).hasMessageContaining("two_confirmed_cases_required");verify(dao,never()).analysis(any());}
 @Test void opaqueReferencesAreValidatedBeforeSql(){assertThatThrownBy(()->service.problem("1 OR 1=1")).hasMessageContaining("invalid_reference");verifyNoInteractions(dao);}
 @Test void analysisSnapshotDoesNotSerializeDatabaseDateTypes(){
  Map<String,Object> g=new HashMap<>();g.put("version",1);g.put("title","材料说明问题");when(dao.group(ref)).thenReturn(g);
  Map<String,Object> first=problem();first.put("createdAt",java.time.LocalDateTime.now());first.put("projectionHash","first");
  String secondRef="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";Map<String,Object> second=problem();second.put("caseRef",secondRef);second.put("projectionHash","second");second.put("createdAt",java.time.LocalDateTime.now());
  when(dao.problem(ref)).thenReturn(first);when(dao.problem(secondRef)).thenReturn(second);
  when(dao.members(ref)).thenReturn(Arrays.asList(Collections.singletonMap("caseRef",ref),Collections.singletonMap("caseRef",secondRef)));
  Map<String,Object> q=new HashMap<>();q.put("requestRef",UUID.randomUUID().toString());q.put("version",1);service.requestAnalysis(ref,q,"ops");
  ArgumentCaptor<Map<String,Object>> capture=ArgumentCaptor.forClass(Map.class);verify(dao).analysis(capture.capture());
  assertThat(String.valueOf(capture.getValue().get("snapshot"))).doesNotContain("createdAt").contains("sampleCount");
  assertThat(String.valueOf(capture.getValue().get("snapshot"))).doesNotContain("evidence_refs");
 }
}
