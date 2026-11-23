<template>
  <div class="traffic-import">
    <h3>流量数据导入（生意参谋 / 千牛）</h3>
    <p class="hint">
      生意参谋 → 商品 → 商品效果 → 下载，或千牛「商品分析」导出明细。
      7 天和 30 天分别导两次、分别导入，两个周期互不覆盖。<br />
      支持 .xlsx / .xls / .csv，按文件内容识别真实格式（生意参谋的 .xls 多是网页表格，直接传即可）。
      文件前面的标题行、统计周期、口径说明会自动跳过；表头带「(人)(件)(元)」单位、
      商品 ID 是链接、数值带 ≈ 或千分位，都能识别。
    </p>

    <div class="period-row">
      <span class="period-label">统计周期</span>
      <template v-if="detectedPeriod">
        <span class="period-note">
          按文件名识别为 {{ detectedPeriod.start }} ~ {{ detectedPeriod.end }}，
          入库以这个区间为准
        </span>
      </template>
      <template v-else>
        <button
          v-for="option in PERIODS"
          :key="option.value"
          class="period-btn"
          :class="{ 'period-btn--active': periodDays === option.value }"
          :disabled="loading"
          @click="periodDays = option.value"
        >
          {{ option.label }}
        </button>
        <span class="period-note">文件名里没有日期，才用这里的档位</span>
      </template>
    </div>

    <div class="file-area">
      <label class="file-label">
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,.xlsm,.xls,.csv"
          class="file-input"
          :disabled="loading"
          @change="onFileChange"
        />
        <span class="file-btn">选择文件</span>
        <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
      </label>
      <button class="btn-primary" :disabled="!selectedFile || loading" @click="upload">
        {{ loading ? '导入中…' : '导入' }}
      </button>
    </div>

    <div v-if="overview && overview.item_count" class="overview-box">
      <div class="overview-head">
        已导入 {{ overview.item_count }} 个商品 · {{ periodLabel(overview.period_days) }}
      </div>
      <div class="metric-grid">
        <div class="metric">
          <div class="metric-k">访客</div>
          <div class="metric-v">{{ overview.totals.visitors.toLocaleString('zh-CN') }}</div>
        </div>
        <div class="metric">
          <div class="metric-k">支付买家</div>
          <div class="metric-v">{{ overview.totals.pay_buyers.toLocaleString('zh-CN') }}</div>
        </div>
        <div class="metric">
          <div class="metric-k">支付转化率</div>
          <div class="metric-v">{{ rate(overview.totals.conversion_rate) }}</div>
        </div>
        <div class="metric">
          <div class="metric-k">加购率</div>
          <div class="metric-v">{{ rate(overview.totals.cart_rate) }}</div>
        </div>
        <div class="metric">
          <div class="metric-k">支付金额</div>
          <div class="metric-v">{{ money(overview.totals.pay_amount) }}</div>
        </div>
        <div class="metric">
          <div class="metric-k">零访客商品</div>
          <div class="metric-v" :class="{ 'metric-v--warn': overview.zero_visitor_items > 0 }">
            {{ overview.zero_visitor_items }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="result" class="result-box">
      <p>
        导入完成：{{ result.imported }} 条（{{ result.period_start }} ~
        {{ result.period_end }}，{{ result.period_days }} 天）
      </p>

      <div class="result-grid">
        <div>
          <div class="result-k">识别到的列（{{ result.recognized.length }}）</div>
          <ul class="col-list">
            <li v-for="col in result.recognized" :key="col.field">
              {{ col.column }} → {{ FIELD_LABELS[col.field] || col.field }}
            </li>
          </ul>
        </div>
        <div v-if="result.unknown_columns.length">
          <div class="result-k warn">未识别（已忽略）</div>
          <ul class="col-list">
            <li v-for="(col, i) in result.unknown_columns" :key="i">{{ col }}</li>
          </ul>
        </div>
      </div>

      <details v-if="result.errors.length">
        <summary>无效行 {{ result.errors.length }} 条</summary>
        <ul class="error-list">
          <li v-for="(e, i) in result.errors" :key="i">{{ e }}</li>
        </ul>
      </details>

      <p v-if="result.unknown_columns.length" class="tip">
        有列没认出来，说明千牛的表头和我预置的别名不一致。把表头发我，加一条映射就行。
      </p>
    </div>

    <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { fetchTrafficOverview, importTraffic } from '../api/inspection.js'

const FIELD_LABELS = {
  item_id: '商品 ID',
  title: '商品名称',
  visitors: '访客数',
  page_views: '浏览量',
  pay_buyers: '支付买家数',
  pay_units: '支付件数',
  pay_amount: '支付金额',
  conversion_rate: '支付转化率',
  cart_units: '加购件数',
  fav_units: '收藏件数',
}

const PERIODS = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 1, label: '昨日' },
  { value: 90, label: '近 90 天' },
]

const fileInput = ref(null)
const selectedFile = ref(null)
const detectedPeriod = ref(null)
const periodDays = ref(7)
const loading = ref(false)
const result = ref(null)
const errorMsg = ref(null)
const overview = ref(null)

function periodLabel(value) {
  return PERIODS.find((item) => item.value === value)?.label || `${value} 天`
}

function money(value) {
  if (value === null || value === undefined) return '—'
  return `¥${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function rate(value) {
  if (value === null || value === undefined) return '—'
  return `${(Number(value) * 100).toFixed(2)}%`
}

async function loadOverview() {
  try {
    overview.value = await fetchTrafficOverview({ periodDays: periodDays.value })
  } catch (e) {
    overview.value = null
  }
}

watch(periodDays, loadOverview)
onMounted(loadOverview)

/** 与后端同一套规则：文件名里的日期就是统计周期 */
function parsePeriodFromName(name) {
  const hits = [
    ...String(name || '').matchAll(/(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})/g),
  ].map((m) => `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`)
  if (!hits.length) return null
  const sorted = [hits[0], hits[1] || hits[0]].sort()
  return { start: sorted[0], end: sorted[1] }
}

function onFileChange(event) {
  selectedFile.value = event.target.files[0] || null
  detectedPeriod.value = parsePeriodFromName(selectedFile.value?.name)
  result.value = null
  errorMsg.value = null
}

async function upload() {
  if (!selectedFile.value) return
  loading.value = true
  result.value = null
  errorMsg.value = null
  try {
    result.value = await importTraffic(selectedFile.value, { periodDays: periodDays.value })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.traffic-import { padding: 0; }

h3 {
  font-size: 18px; font-weight: 500; letter-spacing: 0.15px;
  color: var(--text); margin-bottom: 8px;
}

.hint {
  font-size: 13px; color: var(--text-muted); line-height: 1.7; margin-bottom: 20px;
}

.period-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.period-label { font-size: 13px; color: var(--text-secondary); margin-right: 4px; }
.period-btn {
  padding: 6px 14px; font-size: 13px; border-radius: 9999px; cursor: pointer;
  background: var(--surface); color: var(--text-muted);
  border: 1px solid var(--border); transition: all 0.15s;
}
.period-btn--active {
  background: #000; color: #fff; border-color: #000;
}
.period-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.period-note { font-size: 12.5px; color: var(--text-muted); }

.file-area {
  display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
  padding: 14px 18px; background: var(--bg-subtle);
  border: 1px solid var(--border); border-radius: 16px;
}

.file-label { display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1; }
.file-input { display: none; }
.file-btn {
  padding: 6px 14px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 9999px; font-size: 13px; color: var(--text-secondary);
}
.file-name { font-size: 13px; color: var(--text-muted); }

.btn-primary {
  padding: 8px 18px; background: #000; color: #fff; border: none;
  border-radius: 9999px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.overview-box { margin-bottom: 24px; }
.overview-head {
  font-size: 12.5px; color: var(--text-muted); margin-bottom: 10px;
}
.metric-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px;
}
.metric {
  background: var(--surface); border-radius: 12px; padding: 11px 14px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px;
}
.metric-k { font-size: 11.5px; color: var(--text-muted); margin-bottom: 3px; }
.metric-v { font-size: 17px; font-weight: 500; color: var(--text); }
.metric-v--warn { color: #8B3A32; }

.result-box {
  background: var(--bg-subtle); border: 1px solid var(--border);
  border-radius: 16px; padding: 18px 20px; font-size: 13px; color: var(--text-secondary);
}
.result-box > p:first-child { margin: 0 0 14px; color: var(--text); font-weight: 500; }

.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.result-k { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.result-k.warn { color: #8B3A32; }
.col-list { margin: 0; padding-left: 18px; line-height: 1.9; }
.tip { margin: 12px 0 0; font-size: 12px; color: var(--text-muted); }

.error-list { max-height: 220px; overflow: auto; font-size: 12px; }

.error-box {
  margin-top: 16px; padding: 12px 16px; border-radius: 10px;
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; font-size: 13px;
}
</style>
