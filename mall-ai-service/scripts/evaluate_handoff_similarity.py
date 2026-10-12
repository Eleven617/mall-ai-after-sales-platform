"""Small synthetic family holdout; no customer corpus and no cloud calls."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.handoff_projection import project,semantic_text
from app.services.handoff_semantic import model_version,rank
from app.services.embedding_service import get_embeddings

FAMILIES={
 'materials':['不知道换货材料要求','换货凭证怎么准备'],
 'entry':['找不到换货入口','换货在哪里申请'],
 'eligibility':['换货资格不明确，能不能办理','换货是否可以办理'],
 'progress':['换货申请进度不清楚','换货申请多久完成'],
 'policy_conflict':['换货政策说明有冲突','换货政策前后不一致'],
 'system_error':['换货提交失败','换货页面打不开'],
}
def run():
    rows=[(family,text) for family,texts in FAMILIES.items() for text in texts]
    projections=[project('exchange',text) for _,text in rows]
    vectors=get_embeddings([semantic_text(p,'exchange') for p in projections])
    raw=get_embeddings([text for _,text in rows])
    results=[]
    for name,values in [('raw',raw),('template',vectors)]:
        for split,families in [('development',{'materials','entry','eligibility'}),('holdout',{'progress','policy_conflict','system_error'})]:
            selected=[i for i,(family,_) in enumerate(rows) if family in families];correct=0
            for i in selected:
                first=rank(values[i],{str(j):values[j] for j in selected if j!=i},1)[0]
                correct+=rows[int(first[0])][0]==rows[i][0]
            results.append({'representation':name,'split':split,'queryCount':len(selected),'precisionAt1':correct/len(selected),'recallAt1':correct/len(selected),'completeSyntheticLabels':True})
    report={'model':model_version(),'dimension':len(vectors[0]),'fixtureHash':hashlib.sha256(json.dumps(FAMILIES,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'results':results,'thresholdEnabled':False,'externalProviderCalls':0,'limitations':'12 synthetic descriptions, six controlled issue families; templates intentionally collapse known paraphrases. This does not measure discovery of unseen issue types or real customer accuracy.'}
    target=Path(__file__).resolve().parents[2]/'tmp/handoff-semantic-similarity.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()
