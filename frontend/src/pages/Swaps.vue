<template>
  <div>
    <h1 class="brand">对调</h1>
    <p class="muted">先生成周表，再填写两格对调（day + task_id）。pending 对调须双方成员各签名一次，双签齐备后才能确认改表；任一方拒签即为终态。</p>
    <div class="week-card" style="margin-bottom:12px">
      <label>A day <input type="number" v-model.number="form.a_day" /></label>
      <label>A task_id <input type="number" v-model.number="form.a_task" /></label>
      <label>B day <input type="number" v-model.number="form.b_day" /></label>
      <label>B task_id <input type="number" v-model.number="form.b_task" /></label>
      <button @click="request">申请对调</button>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="s in rows" :key="s.id">
        <div>
          #{{ s.id }} D{{ s.a_day }}/T{{ s.a_task }} ↔ D{{ s.b_day }}/T{{ s.b_task }}
          <span class="chip" :class="{ coral: s.status==='pending' }">{{ s.status }}</span>
          <span v-if="s.status==='pending'" class="muted">签名 {{ s.signed_count }}/2</span>
        </div>
        <div style="margin:6px 0; display:flex; gap:8px; flex-wrap:wrap; align-items:center">
          <span class="week-card" style="padding:4px 10px; min-height:0">
            A · {{ s.a.member_name || ('#' + s.a.member_id) }}
            <span class="chip" :class="sideChip(s.a)">{{ signLabel(s.a) }}</span>
          </span>
          <span class="week-card" style="padding:4px 10px; min-height:0">
            B · {{ s.b.member_name || ('#' + s.b.member_id) }}
            <span class="chip" :class="sideChip(s.b)">{{ signLabel(s.b) }}</span>
          </span>
        </div>
        <div v-if="s.status==='pending'" style="display:flex; gap:8px; flex-wrap:wrap">
          <template v-for="side in ['a','b']" :key="side">
            <button class="ghost" :disabled="s[side].signed"
                    @click="sign(s.id, s[side].member_id, 'approve')">
              {{ side.toUpperCase() }} 同意
            </button>
            <button class="ghost" :disabled="s[side].signed"
                    @click="sign(s.id, s[side].member_id, 'reject')">
              {{ side.toUpperCase() }} 拒签
            </button>
          </template>
          <button :disabled="!s.ready_to_confirm" @click="confirm(s.id)">
            确认改表{{ s.ready_to_confirm ? '' : '（缺签名）' }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
const form = ref({ a_day: 0, a_task: 1, b_day: 1, b_task: 1 })
async function load() { rows.value = await api('/swaps') }
async function request() {
  err.value = ''
  try {
    await api('/weeks/1/swaps', { method: 'POST', body: JSON.stringify(form.value) })
    await load()
  } catch (e) { err.value = e.message }
}
async function sign(id, memberId, decision) {
  err.value = ''
  try {
    await api('/swaps/' + id + '/sign', {
      method: 'POST', body: JSON.stringify({ member_id: memberId, decision }),
    })
    await load()
  } catch (e) { err.value = e.message }
}
async function confirm(id) {
  err.value = ''
  try { await api('/swaps/' + id + '/confirm', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
function signLabel(side) {
  return { unsigned: '未签', approved: '已签', rejected: '拒签', unassigned: '缺当事方' }[side.decision] || side.decision
}
function sideChip(side) {
  return { coral: side.decision !== 'approved' }
}
onMounted(load)
</script>
