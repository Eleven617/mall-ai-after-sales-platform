<script setup lang="ts">
import {ref,watch} from 'vue';
import {getAgentTasks} from './api';
import type {AgentTaskPublicView} from './types';
const props=defineProps<{authorization:string;sessionId:string;disabled:boolean}>();
const emit=defineEmits<{prepared:[]}>();
const open=ref(false),busy=ref(false),error=ref('');
const tasks=ref<AgentTaskPublicView[]>([]),selected=ref(''),reason=ref('unspecified'),topic=ref('general'),newIssue=ref(false);
watch(()=>[props.sessionId,props.authorization],()=>{open.value=false;tasks.value=[];selected.value='';error.value='';});
async function show(){
 if(!props.authorization){error.value='请先登录后请求人工。';return;}
 open.value=true;error.value='';
 try{tasks.value=await getAgentTasks(props.sessionId,props.authorization);}catch{error.value='事项列表暂不可读取，仍可选择一般咨询。';}
}
async function prepare(){
 busy.value=true;error.value=''; const session=props.sessionId;
 const conversation=await fetch('/api/customer-service/conversations/'+encodeURIComponent(session),{method:'POST',headers:{Authorization:props.authorization}}).catch(()=>null);
 if(!conversation?.ok){error.value='请先选择或创建当前账号的会话。';busy.value=false;return;}
 try{
 const response=await fetch('/api/human-handoffs/prepare',{method:'POST',headers:{'Content-Type':'application/json',Authorization:props.authorization},body:JSON.stringify({session_id:session,task_ref:selected.value||null,reason:reason.value,topic:topic.value,new_issue:newIssue.value})});
 if(!response.ok)throw new Error('交接预览暂不可用，请刷新后再试。');
 if(session!==props.sessionId)return;
 open.value=false;emit('prepared');
 }catch(e){error.value=e instanceof Error?e.message:'交接预览未完成';}finally{busy.value=false;}
}
</script>
<template>
 <div class="human-entry">
 <button type="button" class="secondary-button" :disabled="disabled||busy" @click="show">转人工</button>
 <p v-if="error" role="alert">{{error}}</p>
 <section v-if="open" aria-label="人工交接选择">
 <h3>需要人工协助</h3><p>确认交接卡后登记案件，等待处理人员领取。无需填写订单号。</p>
 <label>关联事项 <select v-model="selected"><option value="">一般咨询</option><option v-for="task in tasks" :key="task.task_ref" :value="task.task_ref">{{task.goal}}</option></select></label>
 <label>业务类型 <select v-model="topic"><option value="general">一般咨询</option><option value="policy">政策咨询</option><option value="logistics">物流</option><option value="refund">退款</option><option value="return">退货</option><option value="exchange">换货</option><option value="repair">维修</option><option value="application_follow_up">申请进度</option></select></label>
 <label>原因（可不填） <select v-model="reason"><option value="unspecified">不填写</option><option value="human_preference">希望人工帮助</option><option value="intent_misunderstood">没有理解我的意思</option><option value="repeated_questions">重复询问信息</option><option value="answer_or_evidence_insufficient">回答没有解决问题</option><option value="tool_or_system_error">系统异常</option><option value="business_dispute">业务争议</option><option value="delay_or_complex_process">流程复杂或等待过久</option></select></label>
 <label v-if="!selected"><input v-model="newIssue" type="checkbox">这是另一件新问题（否则优先返回已有交接）</label>
 <button class="primary-button" :disabled="busy" @click="prepare">查看交接卡</button><button class="secondary-button" @click="open=false">返回对话</button>
 </section>
 </div>
</template>
<style scoped>.human-entry{margin:8px 0}.human-entry section{display:grid;gap:12px;padding:16px;background:#f0fdfa;border:1px solid #99f6e4;border-radius:12px}.human-entry label{display:flex;gap:10px;align-items:center}.human-entry p{font-size:13px}.human-entry select{max-width:100%;padding:7px}</style>
