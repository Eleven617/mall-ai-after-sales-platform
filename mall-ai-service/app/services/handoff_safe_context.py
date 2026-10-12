"""Produce reviewed lexical projections from new turns, never read old transcripts.

Unknown lexemes reject the clause instead of guessing whether they are personal
data. This is a deliberately conservative data-production contract, not a claim
that regular expressions anonymize unrestricted Chinese text.
"""
import hashlib
import json
import re
from app.services.handoff_projection import SENSITIVE

VERSION='safe-lexemes-v1'
WORDS=set('没有 不知道 不清楚 不明白 不能 可以 是否 能否 还能 需要 哪些 怎么 哪里 什么时候 多久 已经 仍然 尚未 未能 无法 不一致 冲突 矛盾 找不到 找到 打不开 失败 报错 异常 提交 申请 办理 换货 退货 退款 维修 物流 政策 订单 商品 耳机 手机 材料 凭证 证明 照片 开箱 视频 录像 寄回 寄到 收货 退回 入口 进度 资格 条件 要求 说明 解释 查询 回答 核实 确认 拒绝 同意 已 提供 补充 收到 完成 处理 解决 未解决 一般 具体 相关 还 再 先 后 现在 之前 但是 可 以 不 是 有 无 能 会 影响 吗 呢 的 了 我 想 要 请 帮 忙 这个 那个 问题 一下 什么 如何 为什么 还有 和 或 与 在 对 于 及 按照 只 尚 不足 等待 消息 没 消费者 客户 客服 人工 转 咨询 联系 说明书 包装 拆封 使用 质量 损坏 瑕疵 退换 费用 运费 承担 商家 平台 时间 到账 原路 支付 账户 审核 发货 收件 快递 单号 检查 结果 建议 准备 还没 尚不 明确 弄懂 还是 给出 有依据 通用 出现 按钮 页面 步骤'.split())
WORDS.update('缺少 缺失 不明确 应该 了解 尚未明确 一般材料 凭证类型 已解释 是否影响 正常 无理由 七天 说明不清楚'.split())
ORDERED=sorted(WORDS,key=lambda s:(-len(s),s))
TOPICS={'exchange':'换货','return':'退货','refund':'退款','repair':'维修','logistics':'物流','policy':'政策'}

def safe_tokens(text):
    if not text or SENSITIVE.search(text) or len(text)>8000:return None
    text=re.sub(r'[\s，。！？、；：“”‘’（）,.!?;:\"\'()]','',text)
    tokens=[]
    while text:
        token=next((word for word in ORDERED if text.startswith(word)),None)
        if token is None:return None
        tokens.append('视频' if token=='录像' else token);text=text[len(token):]
    if not tokens or len(tokens)>160:return None
    return ' '.join(tokens)

def fragments(text,role):
    if SENSITIVE.search(text):return [],True
    result=[];omitted=False
    for clause in re.split(r'[。！？!?\n]',text):
        if not clause.strip():continue
        projected=safe_tokens(clause)
        if projected and any(term in projected for term in ('换货','退货','退款','材料','凭证','视频','寄回','入口','进度','资格','政策','维修','物流')):
            result.append({'ref':'src-'+hashlib.sha256((role+':'+projected).encode()).hexdigest()[:24],'kind':'customer_statement' if role=='user' else 'assistant_explanation','text':projected,'version':VERSION})
        elif projected is None:omitted=True
    return result,omitted

def snapshot(stored,current='',topic='general',task_ref=None,task_goal=None,execution=None,omitted=False):
    pieces=[]
    if topic not in TOPICS:
        for text in [current]+[item['text'] for item in reversed(stored) if item['kind']=='customer_statement']:
            found=[key for key,term in TOPICS.items() if term in text]
            if len(found)==1:topic=found[0];break
            if len(found)>1:omitted=True;stored=[];break
    # General consultations only use the current contiguous topic segment.
    # Task handoff never borrows unbound conversational fragments.
    if not task_ref:
        for item in reversed(stored):
            text=item['text']
            if topic in TOPICS and any(term in text for key,term in TOPICS.items() if key!=topic) and TOPICS[topic] not in text:break
            pieces.insert(0,item)
            if len(pieces)>=8:break
    elif task_goal:
        fresh,rejected=fragments(task_goal,'user');pieces.extend(fresh);omitted|=rejected
    fresh,rejected=fragments(current,'user');pieces.extend(fresh);omitted|=rejected
    for step in (execution or [])[-3:]:
        pieces.append({'ref':'src-'+hashlib.sha256(step.encode()).hexdigest()[:24],'kind':'execution_result','text':step,'version':VERSION})
    truncated=len(pieces)>8;pieces=pieces[-8:]
    value={'version':VERSION,'fragments':pieces,'omitted':omitted,'truncated':truncated,'scope':'task' if task_ref else 'conversation','quality':'READY' if any(x['kind']=='customer_statement' for x in pieces) else 'INSUFFICIENT_CONTEXT'}
    # UTF-8 bytes conservatively upper-bound tokenizer tokens for this closed
    # input. No unsupported claim of exact provider-token counting.
    while len(json.dumps(value,ensure_ascii=False).encode())>6000 or sum(len(x['text']) for x in value['fragments'])>3000:
        value['fragments'].pop(0);value['truncated']=True
    value['quality']='READY' if any(x['kind']=='customer_statement' for x in value['fragments']) else 'INSUFFICIENT_CONTEXT'
    value['hash']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value
