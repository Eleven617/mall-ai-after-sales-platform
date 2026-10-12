"""Local, rebuildable case vectors; Java authorizes both sides of retrieval."""
import hashlib
import math
import os
from pathlib import Path
from app.services.embedding_service import current_dimension, current_model_name, get_embeddings
from app.services.handoff_projection import TEMPLATE_VERSION, semantic_text

def model_version():
    # Include actual packaged weights, not just the configured model name.
    from app.services.embedding_service import _resolve_local_model_path
    return _weight_version(str(_resolve_local_model_path()))

from functools import lru_cache
@lru_cache(maxsize=2)
def _weight_version(path):
    digest=hashlib.sha256()
    for name in ('model_optimized.onnx','tokenizer.json','config.json'):
        with (Path(path)/name).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024), b''):digest.update(chunk)
    return current_model_name()+':'+digest.hexdigest()[:16]

def normalize(vector, dimension=None):
    values=[float(x) for x in vector]
    if len(values)!=(dimension or current_dimension()) or not all(math.isfinite(x) for x in values):
        raise ValueError('invalid_vector')
    norm=math.sqrt(sum(x*x for x in values))
    if not math.isfinite(norm) or norm<=0:raise ValueError('invalid_vector_norm')
    return [x/norm for x in values]

def rank(query, candidates, top_k=5, dimension=None):
    if not 1<=top_k<=20 or len(candidates)>5000:raise ValueError('invalid_search_scope')
    q=normalize(query,dimension)
    scores=[(ref,max(-1.0,min(1.0,sum(a*b for a,b in zip(q,normalize(vector,dimension)))))) for ref,vector in candidates.items()]
    return sorted(scores,key=lambda x:(-x[1],x[0]))[:top_k]

def collection():
    import chromadb
    return chromadb.PersistentClient(path=os.getenv('MALL_CASE_INDEX_PATH','data/handoff-case-index')).get_or_create_collection('handoff-cases-v1',embedding_function=None)

def vector_id(item):
    return hashlib.sha256((item['caseRef']+':'+str(item['version'])+':'+item['projectionHash']+':'+model_version()+':'+item['templateVersion']).encode()).hexdigest()

def index_item(item):
    store=collection()
    if item.get('deletedAt'):
        store.delete(where={'caseRef':item['caseRef']});return 'DELETED'
    vector=normalize(get_embeddings([semantic_text(item['projection'],item['topic'])])[0])
    store.upsert(ids=[vector_id(item)],embeddings=[vector],metadatas=[{'caseRef':item['caseRef'],'version':item['version'],'hash':item['projectionHash'],'model':model_version(),'template':item['templateVersion']}])
    # Only remove older versions. A delayed worker must never remove the
    # vector published by a newer correction while its lease was expiring.
    prior=store.get(where={'caseRef':item['caseRef']},include=['metadatas'])
    obsolete=[key for key,meta in zip(prior['ids'],prior['metadatas']) if meta.get('version',0)<item['version'] and key!=vector_id(item)]
    if obsolete:store.delete(ids=obsolete)
    return 'READY'

def similar(ref,authorization,days=30,cross_topic=False,top_k=5):
    from app.routers.handoff_management import proxy
    from fastapi import HTTPException
    data=proxy('GET',f'/semantic/cases/{ref}/candidates',authorization,params={'days':days,'crossTopic':str(cross_topic).lower()})
    query=data['query'];model=model_version()
    eligible=[p for p in data['items'] if p['quality']=='READY']
    valid=[p for p in eligible if p['indexState']=='READY' and p['embeddingVersion']==model and p['templateVersion']==query['templateVersion']]
    ids=[vector_id(p) for p in valid]+[vector_id(query)]
    found=collection().get(ids=list(dict.fromkeys(ids)),include=['embeddings'])
    vectors=dict(zip(found['ids'],found['embeddings']))
    q=vectors.get(vector_id(query))
    if q is None:raise HTTPException(409,'索引待生成，请稍后刷新')
    by_ref={p['caseRef']:p for p in valid if p['caseRef']!=ref and vector_id(p) in vectors}
    scores=rank(q,{key:vectors[vector_id(p)] for key,p in by_ref.items()},top_k)
    # Fetch the entire authorized scope again, rather than trusting vector metadata.
    latest=proxy('GET',f'/semantic/cases/{ref}/candidates',authorization,params={'days':days,'crossTopic':str(cross_topic).lower()})
    if latest['query']['projectionHash']!=query['projectionHash'] or latest['query']['version']!=query['version'] or latest['query']['indexState']!='READY':raise HTTPException(409,'问题记录已变化，请刷新')
    current={p['caseRef']:p for p in latest['items']}
    result=[]
    for key,score in scores:
        p=current.get(key);old=by_ref[key]
        if p and p['version']==old['version'] and p['projectionHash']==old['projectionHash'] and p['indexState']=='READY':result.append({'score':score,'case':p})
    return {'query_ref':ref,'query_projection_version':query['version'],'model_version':model,'template_version':query['templateVersion'],'days':days,'cross_topic':cross_topic,'eligible_count':len(eligible),'indexed_count':sum(vector_id(p) in vectors for p in valid),'candidates':result,'warnings':['相似分数不是同一问题概率；请人工确认。']}
