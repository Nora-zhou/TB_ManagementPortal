<script setup>
import { ref, onMounted } from 'vue'
import { fetchAccounts, createAccount, updateAccount, deleteAccount, testLogin } from '../api/credentials.js'

const accounts = ref([])
const loading = ref(false)
const error = ref(null)
const showForm = ref(false)
const editingId = ref(null)
const form = ref(blankForm())
const formError = ref(null)
const saving = ref(false)
const testingId = ref(null)

const PLATFORM_LABELS = { qianniu: '千牛工作台', alimama: '阿里妈妈投放后台' }

function blankForm() {
  return { platform: 'qianniu', account_label: '', username: '', password: '', store: 1 }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await fetchAccounts()
    accounts.value = res.items
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function startAdd() {
  editingId.value = null
  form.value = blankForm()
  formError.value = null
  showForm.value = true
}

function startEdit(row) {
  editingId.value = row.id
  form.value = {
    platform: row.platform,
    account_label: row.account_label,
    username: row.username,
    password: '',
    store: row.store,
  }
  formError.value = null
  showForm.value = true
}

async function save() {
  formError.value = null
  if (!form.value.account_label.trim()) { formError.value = '请填写账号名称'; return }
  if (!form.value.username.trim()) { formError.value = '请填写登录用户名'; return }
  if (!editingId.value && !form.value.password) { formError.value = '请填写登录密码'; return }

  saving.value = true
  try {
    if (editingId.value) {
      await updateAccount(editingId.value, {
        account_label: form.value.account_label,
        username: form.value.username,
        store: form.value.store,
        password: form.value.password || null,
      })
    } else {
      await createAccount({ ...form.value })
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  if (!confirm('确认删除该账号？删除后其密码立即失效，抓取任务将无法使用该账号。')) return
  try {
    await deleteAccount(id)
    await load()
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

async function doTestLogin(row) {
  testingId.value = row.id
  try {
    const res = await testLogin(row.id)
    alert(res.message)
    await load()
  } catch (e) {
    alert(e.message || '测试登录失败')
  } finally {
    testingId.value = null
  }
}

const STATUS_LABELS = { ok: '可用', fail: '失败', need_verify: '待验证', unknown: '未测试' }

function fmtTime(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="account-manage">
    <div class="page-header">
      <div>
        <h2 class="page-title">平台账号管理</h2>
        <p class="page-sub">
          用于 RPA 自动登录千牛 / 阿里妈妈抓取费用数据。密码以 AES 加密存储，
          密钥保存在项目根目录 <code>.env</code> 的 <code>RPA_MASTER_KEY</code>，请勿泄露或丢失。
        </p>
      </div>
      <button class="btn-primary" @click="startAdd">+ 新增账号</button>
    </div>

    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <div v-else-if="accounts.length === 0" class="empty-state">
      <p>尚未配置任何平台账号。</p>
      <p class="hint">新增千牛或阿里妈妈账号后，即可在「纯利润分析」页触发 RPA 抓取推广费、平台扣费、运费险等数据。</p>
      <button class="btn-primary" @click="startAdd">+ 新增账号</button>
    </div>

    <div v-else class="table-block">
      <table class="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>平台</th>
            <th>用户名</th>
            <th>密码</th>
            <th>店铺</th>
            <th>登录状态</th>
            <th>最近测试</th>
            <th class="ops">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in accounts" :key="row.id">
            <td class="strong">{{ row.account_label }}</td>
            <td>{{ PLATFORM_LABELS[row.platform] || row.platform }}</td>
            <td>{{ row.username }}</td>
            <td class="mono">{{ row.password_masked }}</td>
            <td>{{ row.store }} 店</td>
            <td>
              <span class="tag" :class="'st-' + row.last_login_status">
                {{ STATUS_LABELS[row.last_login_status] || row.last_login_status }}
              </span>
            </td>
            <td class="muted">{{ fmtTime(row.last_login_at) }}</td>
            <td class="ops">
              <button class="btn-link" :disabled="testingId === row.id" @click="doTestLogin(row)">
                {{ testingId === row.id ? '测试中…' : '测试登录' }}
              </button>
              <button class="btn-link" @click="startEdit(row)">编辑</button>
              <button class="btn-link danger" @click="remove(row.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false">
      <div class="modal">
        <div class="modal-title">{{ editingId ? '编辑账号' : '新增平台账号' }}</div>
        <div class="modal-body">
          <label class="form-label">
            账号名称
            <input v-model="form.account_label" type="text" placeholder="如：店铺A-主号" class="form-input" />
          </label>
          <label class="form-label">
            平台
            <select v-model="form.platform" class="form-input" :disabled="!!editingId">
              <option value="qianniu">千牛工作台</option>
              <option value="alimama">阿里妈妈投放后台</option>
            </select>
          </label>
          <label class="form-label">
            登录用户名
            <input v-model="form.username" type="text" placeholder="手机号 / 会员名" class="form-input" />
          </label>
          <label class="form-label">
            登录密码
            <input v-model="form.password" type="password" :placeholder="editingId ? '留空表示不修改' : '登录密码'" class="form-input" />
          </label>
          <label class="form-label">
            关联店铺
            <select v-model="form.store" class="form-input">
              <option :value="1">1 店</option>
              <option :value="2">2 店</option>
            </select>
          </label>
          <div class="hint">
            阿里妈妈与千牛共用同一套淘宝登录账号，如需分别抓取两个后台的数据，
            可添加两条账号记录（平台分别选择「千牛工作台」与「阿里妈妈投放后台」）。
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showForm = false">取消</button>
          <button class="btn-primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.account-manage { max-width: 1100px; margin: 0 auto; padding: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.page-title { margin-bottom: 6px; }
.page-sub { font-size: 12.5px; color: var(--text-muted); max-width: 620px; line-height: 1.65; margin: 0; }
code { background: var(--bg-subtle); border-radius: 5px; padding: 1px 6px; font-size: 12px; }

.btn-primary {
  border: none; border-radius: 9999px; padding: 8px 18px; font-size: 13.5px; font-weight: 500;
  color: #fff; background: linear-gradient(180deg, #3b82f6, #2563eb); cursor: pointer;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}
.btn-primary:disabled { opacity: 0.55; cursor: not-allowed; }

.btn-ghost {
  border: 1px solid var(--border); border-radius: 9999px; padding: 7px 16px;
  font-size: 13px; color: var(--text-muted); background: var(--surface); cursor: pointer;
}
.btn-ghost:hover { color: var(--text); background: var(--bg-subtle); }

.btn-link { border: none; background: none; padding: 2px 6px; font-size: 12.5px; color: #2563eb; cursor: pointer; border-radius: 6px; }
.btn-link:hover { background: rgba(37, 99, 235, 0.08); }
.btn-link:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-link.danger { color: #dc2626; }
.btn-link.danger:hover { background: rgba(220, 38, 38, 0.08); }

.empty-state {
  background: var(--surface); border-radius: 16px; padding: 48px 32px; text-align: center;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.empty-state p { font-size: 14px; color: var(--text); margin: 0 0 10px; }
.empty-state .hint { font-size: 12.5px; color: var(--text-muted); margin-bottom: 20px; }

.table-block {
  background: var(--surface); border-radius: 16px; padding: 20px 24px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.data-table th { font-size: 12px; font-weight: 500; color: var(--text-muted); }
.data-table .ops { text-align: right; }
.data-table .strong { font-weight: 500; }
.data-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--text-muted); }
.data-table .muted { color: var(--text-muted); font-size: 12px; }

.tag { padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 500; }
.st-ok { background: rgba(5, 150, 105, 0.12); color: var(--success); }
.st-fail { background: rgba(220, 38, 38, 0.1); color: var(--danger); }
.st-need_verify { background: rgba(245, 158, 11, 0.14); color: var(--warning); }
.st-unknown { background: var(--bg-subtle); color: var(--text-muted); }

.status-msg { text-align: center; padding: 40px; color: var(--text-muted); }
.error-msg { padding: 10px 16px; color: #b91c1c; border: 1px solid #fecaca; border-radius: 10px; background: #fef2f2; font-size: 13px; }

.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 24px;
}
.modal { background: var(--surface); border-radius: 18px; width: 480px; max-width: 100%; max-height: 88vh; display: flex; flex-direction: column; }
.modal-title { font-size: 15px; font-weight: 600; padding: 18px 24px 12px; }
.modal-body { padding: 0 24px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.modal-footer { padding: 14px 24px 20px; display: flex; justify-content: flex-end; gap: 10px; }

.form-label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-muted); }
.form-input {
  border: 1px solid var(--border); border-radius: 9px; padding: 7px 11px;
  font-size: 13.5px; outline: none; background: var(--surface); color: var(--text);
}
.form-input:focus { border-color: rgba(37, 99, 235, 0.5); }
.form-input:disabled { background: var(--bg-subtle); color: var(--text-muted); }

.hint { font-size: 12px; color: var(--text-muted); line-height: 1.65; }
.form-error { font-size: 12.5px; color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; border-radius: 9px; padding: 8px 12px; }
</style>
