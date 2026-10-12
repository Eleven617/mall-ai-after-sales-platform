"""Closed phrase projection. Input text is transient, never copied or logged."""
import hashlib
import json
import re

TEMPLATE_VERSION = 'issue-v1'
GOALS = {'exchange': '了解并办理换货', 'return': '了解并办理退货', 'refund': '了解并办理退款',
         'logistics': '了解物流处理', 'policy': '了解适用政策', 'repair': '了解并办理维修',
         'application_follow_up': '了解申请进度', 'general': '解决咨询问题', 'unknown': '解决咨询问题'}
ISSUES = {
    'materials': ('材料要求不清楚', r'材料|凭证|证明|照片'),
    'entry': ('找不到办理入口', r'入口|在哪里申请|哪里办理|怎么申请'),
    'eligibility': ('适用资格尚不明确', r'资格|能不能|是否可以|可不可以'),
    'progress': ('处理进度不明确', r'进度|多久|等待|没消息'),
    'policy_conflict': ('政策说明存在待核实的冲突', r'冲突|矛盾|不一致'),
    'system_error': ('办理过程中出现系统异常', r'报错|打不开|系统异常|提交失败'),
}
SENSITIVE = re.compile(r'\d{5,}|@|https?://|bearer|token|password|密码|密钥|身份证|电话|手机|住址|地址|姓名|我叫', re.I)

def project(topic: str, description: str = '') -> dict:
    # Only approved literals leave this function. Regex is NOT a general redactor.
    rejected = bool(SENSITIVE.search(description))
    # Negated/resolved and conditional statements are deliberately insufficient.
    # Customer confirmation does not excuse inventing an unresolved problem.
    uncertain = bool(re.search(r'已经|已解决|已明白|不需要|无需|不是|没有问题|假如|如果|例如|忽略|指令', description))
    obstacle = bool(re.search(r'不清楚|不明白|不知道|不懂|没弄懂|不理解|哪些|怎么|哪里|找不到|没找到|无法|未|不一致|矛盾|冲突|报错|打不开|异常|失败|多久|能不能|是否可以|可不可以|没消息', description))
    codes = [] if rejected or uncertain or not obstacle else [key for key, (_, pattern) in ISSUES.items() if re.search(pattern, description)]
    result = {'customer_goal': GOALS.get(topic, GOALS['unknown']),
              'unresolved_question': '；'.join(ISSUES[key][0] for key in codes),
              'customer_statement': '', 'issue_codes': codes, 'verified_fact_codes': [], 'evidence_refs': [],
              'content_quality': 'REDACTION_REJECTED' if rejected else ('READY' if codes else 'INSUFFICIENT_CONTEXT'),
              'redaction_version': 'closed-phrases-v1', 'summary_template_version': TEMPLATE_VERSION}
    result['projection_hash'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result

def semantic_text(projection: dict, topic: str) -> str:
    if projection.get('content_quality') != 'READY' or not projection.get('unresolved_question'):
        raise ValueError('insufficient_context')
    return f"主题：{GOALS.get(topic, GOALS['unknown'])}。目标：{projection['customer_goal']}。未解决问题：{projection['unresolved_question']}。"
