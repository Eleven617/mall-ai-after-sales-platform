<script setup lang="ts">
import {ref,watch} from 'vue';
import HandoffProblemGroups from './HandoffProblemGroups.vue';
const props=defineProps<{authorization:string;processorCase?:string}>();
type Item={caseRef:string;source:string;topic:string;customerReason:string;verifiedReason?:string;modelReason?:string;reviewVersion:number;analysisState:string;state:string;stage:string;projectionCleared?:number;context?:{planVersion:number;completedSteps:number;verifiedEvidenceCount:number};history?:Array<{source:string;reason:string;revision:number}>};
type Improvement={improvementRef:string;caseRef:string;reason:string;team:string;state:string;version:number;verificationCode:string};
const items=ref<Item[]>([]),selected=ref<Item|null>(null),improvements=ref<Improvement[]>([]),error=ref(''),days=ref(7),page=ref(1),topic=ref(''),source=ref(''),filterReason=ref(''),reviewReason=ref('unspecified'),team=ref('service'),verification=ref('not_verified'),busy=ref(false);
const total=ref(0),pending=ref(0),customerRequested=ref(0),windowLabel=ref(''),reasons=ref<Array<{reason:string;count:number}>>([]);
const labels:Record<string,string>={human_preference:'希望人工帮助',intent_misunderstood:'意图未理解',repeated_questions:'重复追问',answer_or_evidence_insufficient:'回答或证据不足',tool_or_system_error:'工具或系统异常',capability_or_permission_limit:'能力或权限限制',business_dispute:'业务争议',delay_or_complex_process:'等待或流程复杂',unspecified:'未说明/待核实'};
const topicLabels:Record<string,string>={general:'一般咨询',unknown:'未知',policy:'政策',logistics:'物流',refund:'退款',return:'退货',exchange:'换货',repair:'维修',application_follow_up:'申请跟进'};
const stateLabels:Record<string,string>={QUEUED:'等待领取',CLAIMED:'已领取',IN_REVIEW:'核验中',AWAITING_CUSTOMER_INFORMATION:'等待客户补充',RESOLVED:'已解决',CLOSED:'已关闭',CANCELLED:'已取消',PENDING:'等待分析',RUNNING:'分析中',SUCCEEDED:'分析完成',FAILED:'分析失败，可由人工复核',UNAVAILABLE:'分析暂不可用',OPEN:'待核实',TRIAGED:'已分派',IN_PROGRESS:'处理中',VERIFYING:'验证中'};
const stageLabels:Record<string,string>={created:'已创建',planning:'规划中',executing:'处理中',replanning:'重新规划',waiting_for_user:'等待补充信息',waiting_for_async_task:'等待后台结果',ready_to_commit:'等待确认',committing:'提交中',completed:'已完成',failed:'处理失败',blocked:'需要协助',cancelled:'已取消',waiting_human:'等待人工',unknown:'未知/已清理'};
function localTime(value:string|number){return new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});}
async function api(path:string,method='GET',body?:unknown){const response=await fetch('/api/handoff-management'+path,{method,headers:{Authorization:props.authorization,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!response.ok)throw new Error(response.status===404?'此案件为旧版记录，无新版交接投影。':'操作未完成，请核对身份、权限或版本后刷新。');return response.status===204?null:response.json();}
let loadVersion=0;
async function load(){const version=++loadVersion;if(!props.authorization)return;busy.value=true;error.value='';try{if(props.processorCase){const data=await api('/processor/cases/'+props.processorCase);if(version===loadVersion)selected.value=data;}else{const query=new URLSearchParams({days:String(days.value),page:String(page.value),size:'20'});if(topic.value)query.set('topic',topic.value);if(source.value)query.set('source',source.value);if(filterReason.value)query.set('reason',filterReason.value);const [data,work]=await Promise.all([api('?'+query),api('/improvements')]);if(version!==loadVersion)return;items.value=data.items;total.value=data.totals.total;pending.value=data.totals.pendingInWindow||0;customerRequested.value=data.totals.customerRequested||0;reasons.value=data.reasons;windowLabel.value=localTime(data.windowStart)+' — '+localTime(data.windowEnd);improvements.value=work;}}catch(e){if(version===loadVersion)error.value=(e as Error).message;}finally{if(version===loadVersion)busy.value=false;}}
watch(()=>[props.authorization,props.processorCase],()=>{selected.value=null;items.value=[];improvements.value=[];void load();},{immediate:true});
async function select(item:Item){try{selected.value=await api('/cases/'+item.caseRef);}catch(e){error.value=(e as Error).message;}}
async function review(){if(!selected.value)return;try{selected.value=await api('/processor/cases/'+selected.value.caseRef+'/review','POST',{reason:reviewReason.value,version:selected.value.reviewVersion});}catch(e){error.value=(e as Error).message;}}
async function create(){if(!selected.value)return;try{await api('/improvements','POST',{caseRef:selected.value.caseRef,reason:reviewReason.value,team:team.value});await load();}catch(e){error.value=(e as Error).message;}}
async function advance(item:Improvement){const states=['OPEN','TRIAGED','IN_PROGRESS','VERIFYING','CLOSED'];const next=states[states.indexOf(item.state)+1];if(!next)return;try{await api('/improvements/'+item.improvementRef,'PATCH',{state:next,version:item.version,verificationCode:verification.value});await load();}catch(e){error.value=(e as Error).message;}}
</script>
<template>
<section class="handoff-management"><h2>{{processorCase?'交接背景与原因复核':'人工交接与问题改进'}}</h2>
<p v-if="error" role="alert">{{error}}</p>
<div v-if="!processorCase" class="filters">
<select v-model="days"><option :value="7">近7天</option><option :value="30">近30天</option></select>
<select v-model="topic"><option value="">全部业务</option><option v-for="(label,key) in topicLabels" :key="key" :value="key">{{label}}</option></select>
<select v-model="source"><option value="">全部来源</option><option value="customer_requested">客户主动</option><option value="system_suggested_accepted">接受系统建议</option></select>
<select v-model="filterReason"><option value="">全部原因</option><option v-for="(label,key) in labels" :key="key" :value="key">{{label}}</option></select>
<button :disabled="busy" @click="page=1;load()">查询</button>
<p>筛选总数 {{total}} · 当前页 {{items.length}} · 窗口内案件当前待处理 {{pending}} · 客户主动 {{customerRequested}}</p><p>窗口 [开始,结束)：{{windowLabel}}；业务展示时区 Asia/Shanghai。原因优先人工复核，其次模型初判，再其次客户选择。</p>
<ul><li v-for="item in reasons" :key="item.reason">{{labels[item.reason]||item.reason}}：{{item.count}}</li></ul>
<button v-for="item in items" :key="item.caseRef" @click="select(item)">{{topicLabels[item.topic]}} · {{stateLabels[item.state]||item.state}} · {{labels[item.verifiedReason||item.modelReason||item.customerReason]}}</button>
<div><button :disabled="page===1||busy" @click="page--;load()">上一页</button><span>第 {{page}} 页</span><button :disabled="page*20>=total||busy" @click="page++;load()">下一页</button></div>
</div>
<article v-if="selected"><h3>交接详情</h3><p>客户选择：{{labels[selected.customerReason]}}；业务：{{topicLabels[selected.topic]}}；交接时阶段：{{stageLabels[selected.stage]||selected.stage}}</p><p v-if="selected.projectionCleared">交接背景已超过保留期并清理；案件与审计仍保留。</p><p v-else-if="selected.context">交接时计划版本 {{selected.context.planVersion}}，已完成步骤 {{selected.context.completedSteps}}，有效核验依据 {{selected.context.verifiedEvidenceCount}} 项。人工仍需重新核验当前业务事实。</p><p>分析状态：{{stateLabels[selected.analysisState]||selected.analysisState}}；模型初判：{{labels[selected.modelReason||'unspecified']}}；人工结论：{{labels[selected.verifiedReason||'unspecified']}}</p><p>这里只展示结构化交接信息，客户选择和模型初判均不代表已确认的技术根因。</p>
<ul><li v-for="entry in selected.history" :key="entry.source+entry.revision">{{entry.source}} · 第{{entry.revision}}版 · {{labels[entry.reason]}}</li></ul>
<select v-model="reviewReason"><option v-for="(label,key) in labels" :key="key" :value="key">{{label}}</option></select>
<button v-if="processorCase" @click="review">保存人工复核（须先领取案件）</button>
<template v-else><select v-model="team"><option value="service">客服团队</option><option value="engineering">开发团队</option><option value="policy">政策团队</option></select><button @click="create">创建改进事项</button></template></article>
<HandoffProblemGroups v-if="!processorCase" :authorization="authorization" :case-ref="selected?.caseRef" />
<section v-if="!processorCase"><h3>内部改进事项</h3><p>关闭需要验证结论和关联证据，代码合并不自动代表改善。</p><select v-model="verification"><option value="not_verified">尚未验证</option><option value="regression_passed">回归验证通过</option><option value="manual_verified">人工复核通过</option><option value="no_change_needed">核实无需改动</option></select><article v-for="item in improvements" :key="item.improvementRef"><span>{{labels[item.reason]}} · {{item.team}} · {{item.state}} · v{{item.version}} · 引用 {{item.improvementRef}}</span><button v-if="item.state!=='CLOSED'" @click="advance(item)">推进下一状态</button></article></section>
<button :disabled="busy" @click="load">刷新</button>
</section>
</template>
<style scoped>.handoff-management{margin-top:20px;padding:18px;border:1px solid #cbd5e1;border-radius:12px;background:#f8fafc}.handoff-management article{padding:12px;border:1px solid #ddd;margin:10px 0;background:white}.handoff-management select,.handoff-management button{margin:5px;padding:7px}.handoff-management p{font-size:13px;line-height:1.6}.filters{display:block}</style>
