package com.macro.mall.operations.service;

import com.macro.mall.operations.dao.HandoffSummaryDao;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class HandoffSummaryServiceTest {
    @InjectMocks HandoffSummaryService service;
    @Mock HandoffSummaryDao dao;
    final String ref="case-synthetic", source="src-1234567890abcdef12345678";
    static Map<String,Object> map(Object... pairs){Map<String,Object> value=new HashMap<>();for(int i=0;i<pairs.length;i+=2)value.put((String)pairs[i],pairs[i+1]);return value;}

    Map<String,Object> request() throws Exception {
        Map<String,Object> snapshot=new HashMap<>();
        snapshot.put("fragments",Arrays.asList(map("ref",source,"kind","customer_statement","text","没有 开箱 视频 能否 换货")));
        snapshot.put("omitted",false);snapshot.put("truncated",false);
        when(dao.get(ref)).thenReturn(map("snapshot",new ObjectMapper().writeValueAsString(snapshot)));
        Map<String,Object> summary=new HashMap<>();
        summary.put("customer_goal",map("text","确认缺少开箱视频能否换货","source_refs",Arrays.asList(source)));
        summary.put("unresolved_question",map("text","缺少开箱视频是否影响申请","source_refs",Arrays.asList(source)));
        summary.put("handoff_reason_statement",null);
        for(String key:Arrays.asList("handling_steps","customer_statements","uncertainty_notes"))summary.put(key,new ArrayList<>());
        summary.put("evidence_refs",Arrays.asList(source));
        Map<String,Object> q=new HashMap<>();q.put("ref",ref);q.put("state","SUCCEEDED");q.put("summary",summary);q.put("projection",new HashMap<>());
        return q;
    }

    @Test void opaqueSourceDigitsAreNotPersonalDataAndProjectionIsDerived() throws Exception {
        Map<String,Object> q=request();when(dao.finish(any())).thenReturn(1);when(dao.publish(any())).thenReturn(1);
        service.finish(q);
        assertThat(q.get("projectionHash").toString()).hasSize(64);
        assertThat(q.get("projection").toString()).contains("缺少开箱视频");
        verify(dao).audit(ref,"model","summary-worker");
    }
    @Test void expiredLeaseCannotPublish() throws Exception {
        Map<String,Object> q=request();when(dao.finish(any())).thenReturn(0);
        assertThatThrownBy(()->service.finish(q)).hasMessageContaining("409");verify(dao,never()).publish(any());
    }
    @Test void citationMustBeInEvidenceList() throws Exception {
        Map<String,Object> q=request();((Map<String,Object>)q.get("summary")).put("evidence_refs",Collections.emptyList());
        assertThatThrownBy(()->service.finish(q)).hasMessageContaining("invalid_summary_contract");verify(dao,never()).finish(any());
    }
    @Test void customerClaimCannotBecomeExecutedAction() throws Exception {
        Map<String,Object> q=request();((Map<String,Object>)q.get("summary")).put("handling_steps",Arrays.asList(map("text","完成换货","source_refs",Arrays.asList(source),"result_kind","execution_completed")));
        assertThatThrownBy(()->service.finish(q)).hasMessageContaining("invalid_summary_contract");verify(dao,never()).finish(any());
    }
    @Test void staleHumanCorrectionCannotPublish() throws Exception {
        Map<String,Object> q=request();q.put("version",0);
        assertThatThrownBy(()->service.correct(ref,q,"operator")).hasMessageContaining("409");verify(dao,never()).publish(any());
    }
}
