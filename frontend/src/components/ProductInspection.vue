<template>
  <div class="inspection-page">
    <header class="page-head">
      <h2>商品分析</h2>
      <p class="page-desc">
        输入淘宝商品 ID，抓取页面的标题、价格、SKU、主图、详情图与服务评价，并逐字段标注是否可信。
      </p>
    </header>

    <div class="tabs">
      <button class="tab" :class="{ 'tab--active': tab === 'item' }" @click="switchTab('item')">单商品</button>
      <button class="tab" :class="{ 'tab--active': tab === 'shop' }" @click="switchTab('shop')">店铺体检</button>
    </div>

    <div v-show="tab === 'item'" class="collect-card">
      <div class="collect-form">
        <input
          v-model.trim="itemId"
          class="item-input"
          type="text"
          inputmode="numeric"
          placeholder="商品 ID，例如 1052810876450"
          :disabled="collecting"
          @keyup.enter="startCollect"
        />
        <button :disabled="collecting || !itemId" @click="startCollect">
          {{ collecting ? '采集中…' : '开始采集' }}
        </button>
      </div>
      <label class="headless-option">
        <input v-model="headless" type="checkbox" :disabled="collecting" />
        无头模式（不弹浏览器窗口，但更容易触发滑块验证）
      </label>
      <p class="collect-note">
        采集会真实打开本机浏览器访问商品页，单次约 30–60 秒；同一时间只能跑一个任务。
      </p>
    </div>

    <div v-if="collecting" class="progress-banner">
      <span class="spinner"></span>
      <span>{{ HINTS[hintIndex] }}</span>
      <span class="muted">已用时 {{ elapsed }} 秒</span>
    </div>

    <div v-if="error" class="error-banner">
      <span>{{ error }}</span>
      <button class="close-btn" @click="error = null">×</button>
    </div>

    <!-- ── 采集结果 ────────────────────────────────────────────── -->
    <section v-if="view && tab === 'item'" class="result">
      <div class="result-head">
        <div class="result-title">
          <h3>{{ view.title || '(无标题)' }}</h3>
          <div class="meta">
            <span>{{ view.run_id }}</span>
            <span>{{ view.collected_at }}</span>
            <span>{{ view.source }}</span>
          </div>
        </div>
        <div class="result-actions">
          <a v-if="result.preview_url" class="link-btn" :href="result.preview_url" target="_blank" rel="noopener">
            独立预览页
          </a>
          <a class="link-btn" :href="itemUrl(view.item_id)" target="_blank" rel="noopener">商品原页</a>
        </div>
      </div>

      <div class="verdict" :class="reliable ? 'verdict--ok' : 'verdict--bad'">
        <template v-if="reliable">核心字段（标题 / 价格 / 主图数 / 详情图数）全部采到，可用于下游指标。</template>
        <template v-else>
          核心字段缺失：<strong>{{ coreMissing.map(labelOf).join('、') }}</strong>，本次快照标记为不可信（reliable=0）。
        </template>
      </div>

      <div v-if="itemTraffic && itemTraffic.available" class="item-traffic">
        <div class="diagnosis" :class="`diag--${itemTraffic.diagnosis.code}`">
          <span class="diag-label">{{ itemTraffic.diagnosis.label }}</span>
          <span class="diag-advice">{{ itemTraffic.diagnosis.advice }}</span>
        </div>

        <div class="metric-grid metric-grid--sm">
          <div class="metric">
            <div class="metric-k">近 {{ itemTraffic.period_days }} 天访客</div>
            <div class="metric-v">{{ itemTraffic.item.visitors.toLocaleString('zh-CN') }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">支付买家</div>
            <div class="metric-v">{{ itemTraffic.item.pay_buyers }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">转化率</div>
            <div class="metric-v">{{ pct(itemTraffic.item.conversion_rate) }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">支付金额</div>
            <div class="metric-v">{{ money(itemTraffic.item.pay_amount) }}</div>
          </div>
          <div v-if="itemTraffic.item.bounce_rate != null" class="metric">
            <div class="metric-k">详情页跳出率</div>
            <div class="metric-v">{{ pct(itemTraffic.item.bounce_rate) }}</div>
          </div>
          <div v-if="itemTraffic.item.avg_stay_seconds != null" class="metric">
            <div class="metric-k">平均停留</div>
            <div class="metric-v">{{ itemTraffic.item.avg_stay_seconds.toFixed(1) }} 秒</div>
          </div>
        </div>

        <p class="muted bench">
          全店基准：访客中位数 {{ itemTraffic.benchmark.visitor_p50 }}、整体转化率
          {{ pct(itemTraffic.benchmark.conversion_rate) }}、客单价
          {{ money(itemTraffic.benchmark.aov) }}；本商品访客排名
          {{ itemTraffic.rank.visitor_rank }}/{{ itemTraffic.rank.total }}<template
            v-if="itemTraffic.rank.rate_rank"
          >，转化率排名 {{ itemTraffic.rank.rate_rank }}/{{ itemTraffic.benchmark.meaningful_items }}</template>。
          <template v-if="itemTraffic.gap.lost_revenue > 0">
            若转化率达到均值，可多卖 {{ itemTraffic.gap.lost_buyers }} 单（约
            {{ money(itemTraffic.gap.lost_revenue) }}）。
          </template>
        </p>

        <div v-if="checkup && checkup.available" class="checkup">
          <div class="checkup-head">
            <h4>商品体检</h4>
            <span class="checkup-verdict" :class="{ 'checkup-verdict--bad': checkup.summary.bad > 0 }">
              {{ checkup.summary.verdict }}
            </span>
            <span class="checkup-source" :class="`checkup-source--${checkup.source}`">
              {{ checkup.source === 'llm' ? 'AI 判定' : '规则判定' }}
            </span>
            <button class="link-btn" :disabled="checkupLoading" @click="rerunCheckup">
              {{ checkupLoading ? '判定中…' : '重新判定' }}
            </button>
            <span v-if="!checkup.snapshot_available" class="checkup-note">
              未采集商品页快照，结构项（主图/详情/标题/价格）未检查
            </span>
          </div>
          <ul class="checkup-list">
            <li
              v-for="row in checkup.items"
              :key="row.code"
              class="checkup-row"
              :class="`checkup-row--${row.severity}`"
            >
              <span class="checkup-tag">
                {{ row.severity === 'bad' ? '必改' : row.severity === 'warn' ? '建议' : '达标' }}
              </span>
              <div class="checkup-body">
                <b>{{ row.title }}</b>
                <p class="checkup-problem">{{ row.problem }}</p>
                <p class="checkup-impact">{{ row.impact }}</p>
                <p v-if="row.severity !== 'ok'" class="checkup-action">→ {{ row.action }}</p>
                <p v-if="row.reason" class="checkup-reason">判定依据：{{ row.reason }}</p>
              </div>
            </li>
          </ul>

          <div v-if="checkup.dismissed && checkup.dismissed.length" class="checkup-dismissed">
            <button class="checkup-toggle" @click="dismissedOpen = !dismissedOpen">
              已排除 {{ checkup.dismissed.length }} 项候选
              <span>{{ dismissedOpen ? '收起理由' : '展开理由' }}</span>
            </button>
            <ul v-if="dismissedOpen" class="checkup-dismissed-list">
              <li v-for="row in checkup.dismissed" :key="row.code">
                <b>{{ row.title }}</b>
                <p>{{ row.reason }}</p>
              </li>
            </ul>
          </div>

          <p v-if="checkup.data_gaps && checkup.data_gaps.length" class="checkup-gaps">
            数据不足：{{ checkup.data_gaps.join('；') }}
          </p>
        </div>

        <div class="ai-card ai-card--item">

          <div class="ai-head">
            <div>
              <b>AI 单品诊断</b>
              <span class="ai-sub">7 天 / 30 天流量 + 同期订单 + 商品页快照</span>
            </div>
            <button class="link-btn" :disabled="itemAiLoading" @click="runItemAi(!!itemAi)">
              {{ itemAiLoading ? '分析中…' : itemAi ? '重新生成' : '开始诊断' }}
            </button>
          </div>

          <p v-if="itemAiError" class="ai-error">{{ itemAiError }}</p>

          <template v-else-if="itemAi">
            <div class="ai-stage">
              <span class="ai-stage-tag">{{ stageLabel(itemAi.insight.stage) }}</span>
              <span class="ai-headline">{{ itemAi.insight.headline }}</span>
            </div>

            <ul class="ai-findings">
              <li v-for="(item, index) in itemAi.insight.findings" :key="index">
                <b>{{ item.claim }}</b>
                <span class="ai-evidence">{{ item.evidence }}</span>
                <span class="ai-action">→ {{ item.action }}</span>
              </li>
            </ul>

            <p v-if="itemAi.insight.dont_do && itemAi.insight.dont_do.length" class="ai-dont">
              现在别做：{{ itemAi.insight.dont_do.join('；') }}
            </p>
            <p v-if="itemAi.insight.data_gaps.length" class="ai-gap">
              数据不足以判断：{{ itemAi.insight.data_gaps.join('；') }}
            </p>
            <p class="ai-meta">
              {{ itemAi.source === 'llm' ? `模型 ${itemAi.model}` : '规则生成（未调用大模型）' }}
              <span v-if="itemAi.cached"> · 来自缓存</span>
            </p>
          </template>

          <p v-else class="ai-placeholder">
            诊断会先定位卡在哪一步（曝光 / 点击 / 详情 / 价格 / 信任），再给动作。
            注意：流量报表从访客开始统计，没有曝光和点击率，所以它不会让你去改主图。
          </p>

          <div class="ai-chat">
            <div v-if="!itemChatMessages.length" class="ai-chips">
              <span class="ai-chips-label">常用问题</span>
              <button
                v-for="question in itemSuggestions"
                :key="question"
                class="ai-chip"
                :disabled="itemChatLoading"
                @click="sendItemChat(question)"
              >
                {{ question }}
              </button>
            </div>

            <div v-if="itemChatMessages.length" ref="itemChatLog" class="ai-chat-log">
              <div
                v-for="(message, index) in itemChatMessages"
                :key="index"
                class="ai-msg"
                :class="`ai-msg--${message.role}`"
              >
                <span class="ai-msg-role">{{ message.role === 'user' ? '我' : 'AI' }}</span>
                <p>{{ message.content }}</p>
              </div>
              <div v-if="itemChatLoading" class="ai-msg ai-msg--assistant">
                <span class="ai-msg-role">AI</span>
                <p class="ai-typing">正在看这个商品…</p>
              </div>
            </div>

            <p v-if="itemChatError" class="ai-error">{{ itemChatError }}</p>

            <div class="ai-chat-input">
              <input
                v-model="itemChatInput"
                type="text"
                :disabled="itemChatLoading"
                placeholder="追问这个商品，例如：加购不少但不买，问题在哪？"
                @keyup.enter="sendItemChat()"
              />
              <button
                class="link-btn"
                :disabled="itemChatLoading || !itemChatInput.trim()"
                @click="sendItemChat()"
              >
                发送
              </button>
              <button
                v-if="itemChatMessages.length"
                class="link-btn"
                :disabled="itemChatLoading"
                @click="clearItemChat"
              >
                清空
              </button>
            </div>
          </div>
        </div>
      </div>

      <p v-else-if="itemTraffic && itemTraffic.reason === 'no_data'" class="muted">
        还没有导入流量数据，无法判断这个商品的转化表现。去「数据导入 → 流量数据」上传即可。
      </p>
      <p v-else-if="itemTraffic && itemTraffic.reason === 'item_not_found'" class="muted">
        这个商品不在近 {{ itemTraffic.period_days }} 天的流量报表里（可能没有曝光或未导出）。
      </p>

      <h4>断言检查</h4>
      <div v-if="assertSummary" class="assert-summary">
        <span>共 {{ assertSummary.total }} 项</span>
        <span class="tag-pass">通过 {{ assertSummary.passed }}</span>
        <span :class="assertSummary.failed ? 'tag-fail' : 'tag-pass'">不通过 {{ assertSummary.failed }}</span>
        <span v-if="assertSummary.skipped" class="muted">跳过 {{ assertSummary.skipped }}</span>
        <span v-if="assertSummary.contract_failed" class="tag-fail">
          {{ assertSummary.contract_failed }} 项属数据不可信
        </span>
      </div>
      <table v-if="assertions.length" class="data-table">
        <thead>
          <tr>
            <th class="col-flag">结果</th>
            <th>检查项</th>
            <th class="col-kind">类型</th>
            <th>期望</th>
            <th>实际</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in assertions" :key="item.rule_id" :class="{ 'row-fail': !item.passed }">
            <td class="col-flag">
              <span class="badge" :class="item.passed ? 'badge--ok' : 'badge--bad'">
                {{ item.passed ? '通过' : '不通过' }}
              </span>
            </td>
            <td class="col-rule">
              {{ item.title }}
              <span class="rule-id">{{ item.rule_id }}</span>
            </td>
            <td class="col-kind">
              <span class="kind-tag">{{ item.kind === 'contract' ? '数据' : '规则' }}</span>
            </td>
            <td class="col-nowrap">{{ item.expected }}</td>
            <td>{{ item.actual }}</td>
            <td class="col-msg">{{ item.message || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">本快照没有可判定的断言。</p>
      <p v-if="assertSummary && assertSummary.skipped" class="muted skipped-note">
        另有 {{ assertSummary.skipped }} 项因数据不足跳过：{{ assertSummary.skipped_rules.join('、') }}
      </p>

      <h4>字段对照</h4>
      <table class="data-table">
        <thead>
          <tr><th>字段</th><th>采集值</th><th class="col-flag">可信度</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in fieldRows" :key="row.label">
            <td class="col-key">{{ row.label }}</td>
            <td>{{ row.value }}</td>
            <td class="col-flag">
              <span v-if="row.field" class="badge" :class="row.ok ? 'badge--ok' : 'badge--bad'">
                {{ row.ok ? '可信' : '缺失' }}
              </span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>

      <h4>主图（{{ images.length }} 张）</h4>
      <div v-if="images.length" class="image-grid">
        <figure v-for="(img, idx) in images" :key="idx">
          <img :src="img.url" alt="" loading="lazy" referrerpolicy="no-referrer" />
          <figcaption>
            {{ img.w && img.h ? `${img.w}×${img.h}` : '尺寸未知' }}
            <span v-if="img.ratio === 0.75" class="ratio-tag">3:4</span>
          </figcaption>
        </figure>
      </div>
      <p v-else class="muted">无主图数据</p>

      <h4>SKU</h4>
      <table v-if="skus.length" class="data-table">
        <thead>
          <tr><th>SKU ID</th><th>规格</th><th>价格</th><th>库存</th><th>库存文案</th><th>发货</th></tr>
        </thead>
        <tbody>
          <tr v-for="sku in skus" :key="sku.sku_id">
            <td class="col-mono">{{ sku.sku_id }}</td>
            <td>{{ sku.name || '—' }}</td>
            <td>{{ yuan(sku.price_cents) }}</td>
            <td>{{ sku.stock ?? '—' }}</td>
            <td>{{ sku.quantity_text || '—' }}</td>
            <td>{{ sku.logistics || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">无 SKU 数据</p>

      <h4>服务与评价</h4>
      <table class="data-table">
        <tbody>
          <tr><td class="col-key">邮费</td><td>{{ service.freight || '—' }}</td></tr>
          <tr><td class="col-key">发货时效</td><td>{{ service.ship_aging || '—' }}</td></tr>
          <tr><td class="col-key">发货地</td><td>{{ service.delivery_from || '—' }}</td></tr>
          <tr><td class="col-key">店铺标签</td><td>{{ (service.labels || []).join('、') || '—' }}</td></tr>
          <tr><td class="col-key">评价数</td><td>{{ review.count ?? '—' }}</td></tr>
          <tr><td class="col-key">好评率</td><td>{{ review.favorable_rate || '—' }}</td></tr>
        </tbody>
      </table>

      <h4>页面截图</h4>
      <img v-if="result.shot_url" class="shot" :src="result.shot_url" alt="页面截图" />
      <p v-else class="muted">本次没有截图</p>
    </section>

    <!-- ── 历史记录 ────────────────────────────────────────────── -->
    <!-- ── 店铺体检 ────────────────────────────────────────────── -->
    <section v-show="tab === 'shop'" class="shop-view">
      <div class="shop-head">
        <div>
          <h3>店铺交易结构</h3>
          <p v-if="shop" class="meta-line">
            统计窗口 {{ shop.window.start }} ~ {{ shop.window.end }}（{{ shop.window.days }} 天）
            · {{ shop.window.note }} · 交易关闭不计入成交
          </p>
        </div>
        <button class="link-btn" :disabled="shopLoading" @click="loadShop">
          {{ shopLoading ? '计算中…' : '刷新' }}
        </button>
      </div>

      <p v-if="shopLoading && !shop" class="muted">正在从订单表聚合…</p>

      <div v-else-if="shop" class="shop-body">
        <div class="metric-grid">
          <div class="metric">
            <div class="metric-k">销售额</div>
            <div class="metric-v">{{ money(shop.totals.revenue) }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">销量</div>
            <div class="metric-v">{{ shop.totals.units }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">订单数</div>
            <div class="metric-v">{{ shop.totals.orders }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">客单价</div>
            <div class="metric-v">{{ money(shop.totals.aov) }}</div>
          </div>
          <div class="metric">
            <div class="metric-k">关闭率</div>
            <div class="metric-v" :class="{ 'metric-v--bad': shop.totals.close_rate > 0.15 }">
              {{ pct(shop.totals.close_rate) }}
            </div>
          </div>
          <div class="metric">
            <div class="metric-k">{{ hasPeriodBasis ? '动销率（当期）' : '动销率' }}</div>
            <div class="metric-v">
              {{ pct(sellThrough && sellThrough.rate) }}
              <span class="metric-sub">
                {{ sellThrough ? `${sellThrough.active}/${sellThrough.total}` : '—' }}
              </span>
            </div>
          </div>
        </div>

        <div class="insight-row">
          <div class="insight">
            <b>动销率 {{ pct(sellThrough && sellThrough.rate) }}</b>
            <template v-if="hasPeriodBasis">
              {{ sellThrough.period_start }} ~ {{ sellThrough.period_end }}
              （{{ sellThrough.period_days }} 天）有访客的 {{ sellThrough.total }} 个商品里，
              {{ sellThrough.active }} 个产生成交、
              {{ sellThrough.dead }} 个零成交
              （另有 {{ sellThrough.zero_visitor }} 个商品零曝光，未计入分母）。
            </template>
            <template v-else>
              近 {{ shop.window.days }} 天有成交 {{ shop.sell_through.active }} 个商品，
              {{ shop.sell_through.dead }} 个商品零成交（商品表共 {{ shop.sell_through.total }} 个）。
            </template>
          </div>
          <div class="insight">
            <b>Top10 集中度 {{ pct(shop.concentration.top10_share) }}</b>
            前 10 个商品贡献 {{ money(shop.concentration.top10_revenue) }}，
            占窗口销售额 {{ pct(shop.concentration.top10_share) }}。
          </div>
        </div>

        <h4>价格带分布</h4>
        <table class="data-table">
          <thead>
            <tr>
              <th>成交单价</th>
              <th class="col-num">商品数</th>
              <th class="col-num">销量</th>
              <th class="col-num">销售额</th>
              <th class="col-num">销售额占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="band in shop.price_bands" :key="band.label">
              <td class="col-key">{{ band.label }}</td>
              <td class="col-num">{{ band.items }}</td>
              <td class="col-num">{{ band.units }}</td>
              <td class="col-num">{{ money(band.revenue) }}</td>
              <td class="col-num">{{ pct(band.revenue_share) }}</td>
            </tr>
          </tbody>
        </table>

        <h4>销售额 Top 20</h4>
        <table class="data-table">
          <thead>
            <tr>
              <th class="col-num">#</th>
              <th>商品</th>
              <th class="col-num">销量</th>
              <th class="col-num">销售额</th>
              <th class="col-num">占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in shop.top_items" :key="item.item_id">
              <td class="col-num">{{ item.rank }}</td>
              <td class="col-ellipsis">{{ item.title }}</td>
              <td class="col-num">{{ item.units }}</td>
              <td class="col-num">{{ money(item.revenue) }}</td>
              <td class="col-num">{{ pct(item.revenue_share) }}</td>
            </tr>
          </tbody>
        </table>

        <p class="muted footnote">
          商品表只登记了 {{ shop.totals.items_registered }} 个商品，
          另有 {{ shop.totals.items_unregistered }} 个有成交的商品不在表里（已下架或未导入）。
          动销率已改用当期流量报表的商品集合，不再依赖商品表。
        </p>

        <!-- ── 流量与转化 ────────────────────────────────────── -->
        <div class="section-head">
          <h4>流量与转化</h4>
          <div class="period-switch">
            <button
              v-for="option in [7, 30]"
              :key="option"
              class="period-btn"
              :class="{
                'period-btn--active': trafficDays === option,
                'period-btn--missing': !availableTrafficDays.includes(option),
              }"
              :disabled="trafficLoading"
              :title="availableTrafficDays.includes(option) ? '' : `还没有导入近 ${option} 天的流量报表`"
              @click="changeTrafficDays(option)"
            >
              近 {{ option }} 天
            </button>
          </div>
        </div>

        <p v-if="trafficLoading && !traffic" class="muted">加载中…</p>

        <div v-else-if="traffic && traffic.empty" class="empty-note">
          <template v-if="traffic.reason === 'no_period_for_days'">
            还没有导入近 {{ traffic.period_days }} 天的流量报表。
            <template v-if="traffic.available_periods && traffic.available_periods.length">
              当前已导入的期次：{{ traffic.available_periods.map((p) => p.label).join('、') }}。
            </template>
            去「数据导入 → 流量数据」上传对应周期的文件即可。
          </template>
          <template v-else>
            近 {{ traffic.period_days }} 天没有流量数据。
            去「数据导入 → 流量数据」上传生意参谋导出的文件。
          </template>
        </div>

        <div v-else-if="traffic" class="traffic-body">
          <div class="metric-grid">
            <div class="metric">
              <div class="metric-k">访客</div>
              <div class="metric-v">{{ traffic.totals.visitors.toLocaleString('zh-CN') }}</div>
            </div>
            <div class="metric">
              <div class="metric-k">支付买家</div>
              <div class="metric-v">{{ traffic.totals.buyers }}</div>
            </div>
            <div class="metric">
              <div class="metric-k">支付转化率</div>
              <div class="metric-v">{{ pct(traffic.totals.conversion_rate) }}</div>
            </div>
            <div class="metric">
              <div class="metric-k">访客客单价</div>
              <div class="metric-v">{{ money(traffic.totals.aov) }}</div>
            </div>
            <div class="metric">
              <div class="metric-k">零访客商品</div>
              <div class="metric-v" :class="{ 'metric-v--bad': traffic.distribution.zero_visitor > 0 }">
                {{ traffic.distribution.zero_visitor }}
              </div>
            </div>
            <div class="metric">
              <div class="metric-k">零成交商品</div>
              <div class="metric-v" :class="{ 'metric-v--bad': traffic.distribution.zero_order > 0 }">
                {{ traffic.distribution.zero_order }}
              </div>
            </div>
          </div>

          <div v-if="trafficInsight" class="insight-row">
            <div class="insight">
              <b>{{ trafficInsight.title }}</b>
              {{ trafficInsight.text }}
            </div>
            <div class="insight">
              <b>访客集中度 {{ pct(traffic.concentration.top10_share) }}</b>
              前 10 个商品拿到 {{ traffic.concentration.top10_visitors.toLocaleString('zh-CN') }}
              个访客；访客中位数 {{ traffic.distribution.visitor_p50 }}，
              访客 ≥50 的只有 {{ traffic.distribution.meaningful_items }} 个商品。
            </div>
          </div>

          <div class="ai-card">
            <div class="ai-head">
              <div>
                <b>AI 解读</b>
                <span class="ai-sub">
                  {{
                    aiInsight
                      ? aiWindowText
                      : '固定对比 30 天基线与最近一期，不随上方档位切换'
                  }}
                </span>
              </div>
              <button
                class="link-btn"
                :disabled="aiLoading"
                @click="runAiInsight(!!aiInsight)"
              >
                {{ aiLoading ? '分析中…' : aiInsight ? '重新生成' : '生成解读' }}
              </button>
            </div>

            <p v-if="aiError" class="ai-error">{{ aiError }}</p>

            <template v-else-if="aiInsight">
              <p class="ai-headline">{{ aiInsight.insight.headline }}</p>
              <ul class="ai-findings">
                <li v-for="(item, index) in aiInsight.insight.findings" :key="index">
                  <b>{{ item.claim }}</b>
                  <span class="ai-evidence">{{ item.evidence }}</span>
                  <span class="ai-action">→ {{ item.action }}</span>
                </li>
              </ul>
              <p v-if="aiInsight.insight.data_gaps.length" class="ai-gap">
                数据不足以判断：{{ aiInsight.insight.data_gaps.join('；') }}
              </p>
              <p class="ai-meta">
                {{ aiInsight.source === 'llm' ? `模型 ${aiInsight.model}` : '规则生成（未调用大模型）' }}
                · {{ aiInsight.generated_at }}
                <span v-if="aiInsight.cached"> · 来自缓存</span>
              </p>
            </template>

            <p v-else class="ai-placeholder">
              <template v-if="aiConfigured">
                点击生成：模型会对比两期的日均访客、转化率、客单价与零成交占比，
                给出可执行的结论。
              </template>
              <template v-else>
                未配置大模型，将使用规则结论。在项目根目录 .env 填
                AI_BASE_URL / AI_API_KEY / AI_MODEL 即可接入。
              </template>
            </p>

            <div class="ai-chat">
              <div v-if="!chatMessages.length" class="ai-chips">
                <span class="ai-chips-label">常用问题</span>
                <button
                  v-for="question in chatSuggestions"
                  :key="question"
                  class="ai-chip"
                  :disabled="chatLoading"
                  @click="sendChat(question)"
                >
                  {{ question }}
                </button>
              </div>

              <div v-if="chatMessages.length" ref="chatLog" class="ai-chat-log">
                <div
                  v-for="(message, index) in chatMessages"
                  :key="index"
                  class="ai-msg"
                  :class="`ai-msg--${message.role}`"
                >
                  <span class="ai-msg-role">{{ message.role === 'user' ? '我' : 'AI' }}</span>
                  <p>{{ message.content }}</p>
                </div>
                <div v-if="chatLoading" class="ai-msg ai-msg--assistant">
                  <span class="ai-msg-role">AI</span>
                  <p class="ai-typing">正在看数据…</p>
                </div>
              </div>

              <p v-if="chatError" class="ai-error">{{ chatError }}</p>

              <div class="ai-chat-input">
                <input
                  v-model="chatInput"
                  type="text"
                  :disabled="chatLoading"
                  :placeholder="
                    aiConfigured
                      ? '继续追问，例如：如果只改三件事，先改哪三件？'
                      : '未配置大模型，暂时不能对话'
                  "
                  @keyup.enter="sendChat"
                />
                <button
                  class="link-btn"
                  :disabled="chatLoading || !chatInput.trim()"
                  @click="sendChat"
                >
                  发送
                </button>
                <button
                  v-if="chatMessages.length"
                  class="link-btn"
                  :disabled="chatLoading"
                  @click="clearChat"
                >
                  清空
                </button>
              </div>
            </div>
          </div>

          <h4>按访客量分档</h4>
          <table class="data-table">
            <thead>
              <tr>
                <th>访客档</th>
                <th class="col-num">商品数</th>
                <th class="col-num">访客</th>
                <th class="col-num">买家</th>
                <th class="col-num">转化率</th>
                <th class="col-num">销售额</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="band in traffic.bands" :key="band.label">
                <td class="col-key">{{ band.label }}</td>
                <td class="col-num">{{ band.items }}</td>
                <td class="col-num">{{ band.visitors.toLocaleString('zh-CN') }}</td>
                <td class="col-num">{{ band.buyers }}</td>
                <td class="col-num">{{ pct(band.conversion_rate) }}</td>
                <td class="col-num">{{ money(band.revenue) }}</td>
              </tr>
            </tbody>
          </table>

          <h4>高流量低转化（最该先改的）</h4>
          <p v-if="!traffic.suspects.length" class="muted">
            没有命中。判定条件：访客 ≥ {{ traffic.suspect_rule.min_visitors }}，
            且转化率低于店铺均值 {{ pct(traffic.suspect_rule.threshold_rate) }}。
          </p>
          <template v-else>
            <table class="data-table">
              <thead>
                <tr>
                  <th>商品</th>
                  <th class="col-num">访客</th>
                  <th class="col-num">买家</th>
                  <th class="col-num">转化率</th>
                  <th class="col-num">差均值</th>
                  <th class="col-num">少卖人数</th>
                  <th class="col-num">少卖金额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in traffic.suspects" :key="item.item_id">
                  <td class="col-ellipsis">{{ item.title || item.item_id }}</td>
                  <td class="col-num">{{ item.visitors }}</td>
                  <td class="col-num">{{ item.pay_buyers }}</td>
                  <td class="col-num">{{ pct(item.conversion_rate) }}</td>
                  <td class="col-num">{{ item.gap_pp }} pp</td>
                  <td class="col-num">{{ item.lost_buyers }}</td>
                  <td class="col-num">{{ money(item.lost_revenue) }}</td>
                </tr>
              </tbody>
            </table>
            <p class="muted footnote">
              少卖金额 =（店铺平均转化率 {{ pct(traffic.totals.conversion_rate) }}
              − 该商品转化率）× 访客 × 客单价 {{ money(traffic.totals.aov) }}，
              是「假如达到平均水平能多卖多少」，不是实际亏的钱。
            </p>
          </template>
        </div>
      </div>
    </section>

    <section v-show="tab === 'item'" class="history">
      <div class="history-head">
        <h4>最近采集</h4>
        <button class="link-btn" :disabled="loadingHistory" @click="loadHistory">刷新</button>
      </div>
      <p v-if="!history.length" class="muted">还没有采集记录。</p>
      <table v-else class="data-table">
        <thead>
          <tr><th>采集时间</th><th>商品 ID</th><th>标题</th><th>价格</th><th class="col-num">主图</th><th class="col-num">详情图</th><th class="col-flag">可信</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="row in history"
            :key="row.run_id"
            class="history-row"
            @click="loadSnapshot(row.run_id)"
          >
            <td class="col-nowrap">{{ row.collected_at }}</td>
            <td class="col-mono">{{ row.item_id }}</td>
            <td class="col-ellipsis">{{ row.title || '—' }}</td>
            <td>{{ yuan(row.price_cents) }}</td>
            <td class="col-num">{{ row.image_count ?? '—' }}</td>
            <td class="col-num">{{ row.detail_image_count ?? '—' }}</td>
            <td class="col-flag">
              <span class="badge" :class="row.reliable ? 'badge--ok' : 'badge--bad'">
                {{ row.reliable ? '齐' : '缺' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  collectItem,
  fetchAiStatus,
  fetchItemTraffic,
  fetchShopMetrics,
  fetchSnapshot,
  fetchSnapshots,
  fetchTrafficAnalysis,
  fetchTrafficPeriods,
  generateAiInsight,
  chatWithAi,
  generateItemInsight,
  chatWithItemAi,
  fetchItemCheckup,
} from '../api/inspection.js'

const route = useRoute()
const router = useRouter()

const HINTS = [
  '正在打开浏览器窗口…',
  '正在加载商品页…',
  '正在解析页面数据…',
  '正在抓取详情长图…',
  '正在生成预览…',
]

const FIELD_LABELS = {
  title: '标题',
  price_cents: '主价',
  image_count: '主图张数',
  detail_image_count: '详情图张数',
  sales_text: '月销',
  review_count: '评价数',
  sku_json: 'SKU',
  service_json: '服务',
  stock_total: '库存',
  image_meta: '图片元数据',
}

const tab = ref('item')
const shop = ref(null)
const shopLoading = ref(false)
const traffic = ref(null)
const trafficDays = ref(7)
const trafficLoading = ref(false)
const trafficPeriods = ref([])
const itemTraffic = ref(null)
const aiInsight = ref(null)
const aiLoading = ref(false)
const aiError = ref(null)
const aiConfigured = ref(false)
const chatMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatError = ref(null)
const chatLog = ref(null)
const checkup = ref(null)
const checkupLoading = ref(false)
const dismissedOpen = ref(false)
let checkupItemId = ''
const itemAi = ref(null)
const itemAiLoading = ref(false)
const itemAiError = ref(null)
const itemChatMessages = ref([])
const itemChatInput = ref('')
const itemChatLoading = ref(false)
const itemChatError = ref(null)
const itemChatLog = ref(null)

const itemId = ref('')
const headless = ref(false)
const collecting = ref(false)
const elapsed = ref(0)
const hintIndex = ref(0)
const loadingHistory = ref(false)
const error = ref(null)
const result = ref(null)
const history = ref([])

let timer = null

const view = computed(() => result.value?.snapshot ?? null)
const images = computed(() => view.value?.image_meta ?? [])
const skus = computed(() => view.value?.sku ?? [])
const service = computed(() => view.value?.service ?? {})
const review = computed(() => view.value?.review ?? {})
const reliable = computed(() => result.value?.reliable === 1)
const coreMissing = computed(() => result.value?.core_missing ?? [])
const assertions = computed(() => result.value?.assertions?.results ?? [])
const assertSummary = computed(() => result.value?.assertions?.summary ?? null)

const hasPeriodBasis = computed(() => !!shop.value?.sell_through_period)

const sellThrough = computed(
  () => shop.value?.sell_through_period || shop.value?.sell_through || null,
)

const aiWindowText = computed(() => {
  const windowInfo = aiInsight.value?.window
  if (!windowInfo) return ''
  const baseline = `${windowInfo.baseline.days} 天（${windowInfo.baseline.start} ~ ${windowInfo.baseline.end}）`
  if (!windowInfo.recent) return `基于 ${baseline}`
  return `对比 ${baseline} 与 ${windowInfo.recent.days} 天（${windowInfo.recent.start} ~ ${windowInfo.recent.end}）`
})

function shortTitle(title) {
  const text = String(title || '').trim()
  return text.length > 12 ? `${text.slice(0, 12)}…` : text
}

// 预设问题：按「先定位问题 → 再定动作 → 最后验数据」的顺序排，
// 每条都必须能用当前喂给模型的数据回答，不能问流量来源、竞品、成本这类没有的数据。
const chatSuggestions = computed(() => {
  const items = []
  const top = traffic.value?.suspects?.[0]
  if (top && top.title) {
    const rate = (top.conversion_rate * 100).toFixed(2)
    items.push(`「${shortTitle(top.title)}」访客 ${top.visitors}、转化 ${rate}%，该怎么改？`)
  }
  items.push(
    '这家店现在最大的问题是什么？',
    '流量涨了转化没涨，问题出在哪一步？',
    '零成交商品里，没曝光和有曝光但没转化的各占多少？',
    '如果这周只改 3 个商品，改哪 3 个？',
    '哪些商品该考虑下架或重做？',
    '客单价下滑，可能是什么原因？',
    '这批数据可信吗？哪些结论现在还不能下？',
  )
  return items
})

const availableTrafficDays = computed(() => [
  ...new Set(trafficPeriods.value.map((period) => period.period_days)),
])

const trafficInsight = computed(() => {
  const data = traffic.value
  if (!data || data.empty || !data.totals.visitors) return null

  const overall = data.totals.conversion_rate || 0
  const topBand = data.bands.find((band) => band.label.startsWith('100+'))
  if (!topBand || topBand.conversion_rate == null) return null

  const rate = topBand.conversion_rate
  const lower = rate < overall * 0.9
  return {
    title: `100+ 访客档转化率 ${(rate * 100).toFixed(2)}%`,
    text: lower
      ? `比全店 ${(overall * 100).toFixed(2)}% 低 ${((overall - rate) * 100).toFixed(2)} 个百分点。流量最大的 ${topBand.items} 个商品反而最不转化，优先查主图与详情页。`
      : `与全店 ${(overall * 100).toFixed(2)}% 持平或更高，流量分配与承接能力匹配。`,
  }
})

const fieldRows = computed(() => {
  const v = view.value
  if (!v) return []
  const flags = v.field_reliable ?? {}
  const rows = [
    ['商品 ID', v.item_id, null],
    ['标题', v.title || '—', 'title'],
    ['主价', yuan(v.price_cents), 'price_cents'],
    ['券后价', yuan(v.promo_price_cents), null],
    ['SKU 价格区间', `${yuan(v.price_min_cents)} ~ ${yuan(v.price_max_cents)}`, null],
    ['主图张数', v.image_count ?? '—', 'image_count'],
    ['详情图张数', v.detail_image_count ?? '—', 'detail_image_count'],
    ['月销', v.sales_text || '—', 'sales_text'],
    ['库存合计', v.stock_total ?? '—', 'stock_total'],
    ['商品状态', v.item_status || '—', null],
    ['评价数', v.review_count ?? '—', 'review_count'],
    ['数据来源', v.source || '—', null],
    ['采集时间', v.collected_at || '—', null],
  ]
  return rows.map(([label, value, field]) => ({
    label,
    value,
    field,
    ok: field ? Boolean(flags[field]) : false,
  }))
})

function labelOf(field) {
  return FIELD_LABELS[field] || field
}

function yuan(cents) {
  if (cents === null || cents === undefined) return '—'
  return `¥${(cents / 100).toFixed(2)}`
}

function money(value) {
  if (value === null || value === undefined) return '—'
  return `¥${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function pct(value) {
  if (value === null || value === undefined) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function itemUrl(id) {
  return `https://item.taobao.com/item.htm?id=${id}`
}

function startTimer() {
  elapsed.value = 0
  hintIndex.value = 0
  timer = setInterval(() => {
    elapsed.value += 1
    hintIndex.value = Math.min(HINTS.length - 1, Math.floor(elapsed.value / 8))
  }, 1000)
}

function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

async function startCollect() {
  if (collecting.value || !itemId.value) return
  error.value = null
  collecting.value = true
  startTimer()
  try {
    result.value = await collectItem(itemId.value, { headless: headless.value })
    router.replace({ query: { item: itemId.value } })
    await Promise.all([loadHistory(), loadItemTraffic(itemId.value)])
  } catch (e) {
    error.value = e.message
  } finally {
    collecting.value = false
    stopTimer()
  }
}

async function loadSnapshot(runId) {
  error.value = null
  try {
    result.value = await fetchSnapshot(runId)
    itemId.value = result.value.snapshot.item_id
    await loadItemTraffic(itemId.value)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    error.value = e.message
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const data = await fetchSnapshots({ limit: 20 })
    history.value = data.items
  } catch (e) {
    error.value = e.message
  } finally {
    loadingHistory.value = false
  }
}

async function loadShop() {
  shopLoading.value = true
  error.value = null
  try {
    shop.value = await fetchShopMetrics({ days: 90 })
  } catch (e) {
    error.value = e.message
  } finally {
    shopLoading.value = false
  }
}

function switchTab(name) {
  tab.value = name
  if (name !== 'shop') return
  if (!shop.value) loadShop()
  if (!traffic.value) loadTraffic()
  loadAiStatus()
}

async function loadTraffic() {
  trafficLoading.value = true
  error.value = null
  try {
    if (!trafficPeriods.value.length) await loadTrafficPeriods()
    traffic.value = await fetchTrafficAnalysis({ periodDays: trafficDays.value })
  } catch (e) {
    error.value = e.message
  } finally {
    trafficLoading.value = false
  }
}

async function loadAiStatus() {
  try {
    aiConfigured.value = (await fetchAiStatus()).configured
  } catch {
    aiConfigured.value = false
  }
}

async function runAiInsight(refresh = false) {
  aiLoading.value = true
  aiError.value = null
  try {
    const data = await generateAiInsight({ refresh })
    if (!data.available) {
      aiInsight.value = null
      aiError.value = '没有可分析的流量数据，先导入报表。'
      return
    }
    aiInsight.value = data
  } catch (e) {
    aiInsight.value = null
    aiError.value = e.message
  } finally {
    aiLoading.value = false
  }
}

function scrollChatToBottom() {
  nextTick(() => {
    if (chatLog.value) chatLog.value.scrollTop = chatLog.value.scrollHeight
  })
}

async function sendChat(preset) {
  const text = (typeof preset === 'string' ? preset : chatInput.value).trim()
  if (!text || chatLoading.value) return

  chatMessages.value.push({ role: 'user', content: text })
  chatInput.value = ''
  chatLoading.value = true
  chatError.value = null
  scrollChatToBottom()

  try {
    const data = await chatWithAi({ messages: chatMessages.value })
    if (data.reply) {
      chatMessages.value.push({ role: 'assistant', content: data.reply })
    } else {
      chatError.value =
        data.reason === 'no_data' ? '还没有可分析的流量数据。' : '没有返回内容。'
    }
    if (data.error) chatError.value = '模型调用失败，稍后再试。'
  } catch (e) {
    chatError.value = e.message
  } finally {
    chatLoading.value = false
    scrollChatToBottom()
  }
}

function clearChat() {
  chatMessages.value = []
  chatError.value = null
}

// ── 单品 AI ──

const STAGE_LABELS = {
  exposure: '卡在曝光',
  click: '卡在点击',
  detail: '卡在详情页',
  price: '卡在价格',
  trust: '卡在信任',
  deal: '转化正常',
  unclear: '暂无法定位',
}

function stageLabel(stage) {
  return STAGE_LABELS[stage] || '暂无法定位'
}

// 只问当前数据能回答的：流量、加购收藏、订单、页面结构。
// 问「竞品价格」「搜索排名」「投放 ROI」这类，模型只能编。
const itemSuggestions = computed(() => [
  '这个商品现在最该改的一处是什么？',
  '有访客没成交，问题卡在哪一步？',
  '加购和收藏不少但不买，为什么？',
  '该不该下架或重做？',
  '这个商品值不值得继续投入？',
  '和全店平均水平比，差在哪？',
])

async function runItemAi(refresh = false) {
  if (!itemId.value) return
  itemAiLoading.value = true
  itemAiError.value = null
  try {
    const data = await generateItemInsight({ itemId: itemId.value, refresh })
    if (!data.available) {
      itemAi.value = null
      itemAiError.value =
        data.reason === 'item_not_found'
          ? '这个商品不在流量报表里（可能没有曝光或未导出）。'
          : '还没有可分析的流量数据。'
      return
    }
    itemAi.value = data
  } catch (e) {
    itemAi.value = null
    itemAiError.value = e.message
  } finally {
    itemAiLoading.value = false
  }
}

function scrollItemChat() {
  nextTick(() => {
    if (itemChatLog.value) itemChatLog.value.scrollTop = itemChatLog.value.scrollHeight
  })
}

async function sendItemChat(preset) {
  const text = (typeof preset === 'string' ? preset : itemChatInput.value).trim()
  if (!text || itemChatLoading.value || !itemId.value) return

  itemChatMessages.value.push({ role: 'user', content: text })
  itemChatInput.value = ''
  itemChatLoading.value = true
  itemChatError.value = null
  scrollItemChat()

  try {
    const data = await chatWithItemAi({
      itemId: itemId.value,
      messages: itemChatMessages.value,
    })
    if (data.reply) {
      itemChatMessages.value.push({ role: 'assistant', content: data.reply })
    } else {
      itemChatError.value = '没有返回内容。'
    }
    if (data.error) itemChatError.value = '模型调用失败，稍后再试。'
  } catch (e) {
    itemChatError.value = e.message
  } finally {
    itemChatLoading.value = false
    scrollItemChat()
  }
}

function clearItemChat() {
  itemChatMessages.value = []
  itemChatError.value = null
}

async function loadTrafficPeriods() {
  try {
    const data = await fetchTrafficPeriods()
    trafficPeriods.value = data.periods || []
    const days = data.period_days || []
    if (days.length && !days.includes(trafficDays.value)) {
      trafficDays.value = days[0]
    }
  } catch {
    trafficPeriods.value = []
  }
}

async function loadItemTraffic(id) {
  if (!id) return
  checkupItemId = id
  // 换了商品就清掉上一个商品的诊断和对话，避免张冠李戴
  itemAi.value = null
  itemAiError.value = null
  itemChatMessages.value = []
  itemChatError.value = null
  checkup.value = null
  dismissedOpen.value = false
  try {
    const [trafficData, checkupData] = await Promise.all([
      fetchItemTraffic(id, { periodDays: 7 }),
      fetchItemCheckup(id).catch(() => null),
    ])
    itemTraffic.value = trafficData
    checkup.value = checkupData
  } catch {
    itemTraffic.value = null
  }
}

/** 重新判定：跳过后端判定缓存，强制再跑一遍规则层 + 判定层。 */
async function rerunCheckup() {
  if (!checkupItemId || checkupLoading.value) return
  checkupLoading.value = true
  try {
    checkup.value = await fetchItemCheckup(checkupItemId, { refresh: true })
    dismissedOpen.value = checkup.value?.dismissed?.length > 0
  } catch {
    // 判定失败就保留上一次结果，不额外打扰用户
  } finally {
    checkupLoading.value = false
  }
}

function changeTrafficDays(days) {
  if (trafficDays.value === days) return
  trafficDays.value = days
  loadTraffic()
}

onMounted(() => {
  if (route.query.item) itemId.value = String(route.query.item)
  loadHistory()
})

onUnmounted(stopTimer)
</script>

<style scoped>
.inspection-page { max-width: 1000px; margin: 0 auto; }

.page-head { margin-bottom: 20px; }
.page-head h2 { margin: 0 0 6px; font-size: 24px; font-weight: 500; color: var(--text); }
.page-desc { margin: 0; font-size: 13.5px; color: var(--text-muted); letter-spacing: 0.14px; }

.collect-card {
  background: var(--surface); border-radius: 16px; padding: 20px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 4px 4px;
  margin-bottom: 20px;
}
.collect-form { display: flex; gap: 10px; }
.item-input {
  flex: 1; padding: 9px 14px; font-size: 14px; letter-spacing: 0.14px;
  border: 1px solid var(--border); border-radius: 8px; outline: none;
  background: var(--surface); color: var(--text);
}
.item-input:focus { border-color: rgba(0,0,0,0.3); box-shadow: 0 0 0 3px rgba(147,197,253,0.45); }
.headless-option {
  display: flex; align-items: center; gap: 6px;
  margin-top: 12px; font-size: 12.5px; color: var(--text-muted); cursor: pointer;
}
.collect-note { margin: 8px 0 0; font-size: 12px; color: var(--text-muted); }

button {
  padding: 8px 18px; background: #000; color: #fff; border: none; border-radius: 9999px;
  cursor: pointer; font-size: 13px; font-weight: 500; white-space: nowrap;
  transition: background 0.15s;
}
button:hover:not(:disabled) { background: #222; }
button:disabled { opacity: 0.45; cursor: not-allowed; }

.progress-banner {
  display: flex; align-items: center; gap: 10px;
  background: #F2F5F1; border-left: 2px solid #2F5D50; color: #2A4A40;
  padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 16px;
}
.spinner {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2px solid rgba(47,93,80,0.25); border-top-color: #2F5D50;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-banner {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  padding: 10px 16px; border-radius: 10px; font-size: 13px; margin-bottom: 16px;
}
.close-btn { background: none; color: #b91c1c; padding: 0 4px; font-size: 16px; border-radius: 4px; }

.result-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
.result-title h3 { margin: 0 0 4px; font-size: 17px; font-weight: 500; line-height: 1.5; color: var(--text); }
.meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-muted); }
.result-actions { display: flex; gap: 8px; flex-shrink: 0; }
.link-btn {
  display: inline-block; padding: 5px 14px; border-radius: 9999px; text-decoration: none;
  font-size: 12.5px; font-weight: 500; color: var(--text-secondary);
  background: var(--surface); border: 1px solid var(--border); cursor: pointer;
}
.link-btn:hover { background: var(--bg-subtle); }

.verdict { padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 8px; }
.verdict--ok { background: #E1F5EE; color: #0F6E56; }
.verdict--bad { background: #FBEEEC; color: #8B3A32; }

h4 { margin: 26px 0 10px; font-size: 14px; font-weight: 500; color: var(--text); letter-spacing: 0.15px; }

.data-table {
  width: 100%; border-collapse: collapse; background: var(--surface);
  border-radius: 12px; overflow: hidden; font-size: 13px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px;
}
.data-table th, .data-table td {
  text-align: left; padding: 9px 14px; border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.data-table th { font-size: 12px; font-weight: 500; color: var(--text-muted); }
.data-table tbody tr:last-child td { border-bottom: none; }
.col-key { color: var(--text-muted); white-space: nowrap; width: 130px; }
.col-flag { width: 88px; white-space: nowrap; }
.col-num { text-align: right; width: 68px; }
.col-mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
.col-nowrap { white-space: nowrap; }
.col-ellipsis { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.col-kind { width: 62px; }
.col-rule { white-space: nowrap; }
.col-msg { color: var(--text-muted); font-size: 12.5px; max-width: 300px; }
.rule-id {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10.5px; color: var(--text-muted); margin-left: 6px; letter-spacing: 0;
}
.kind-tag {
  display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 100px;
  background: var(--bg-subtle); color: var(--text-secondary);
}
.row-fail { background: #FEF8F7; }
.assert-summary {
  display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
  font-size: 13px; color: var(--text-secondary); padding: 2px 2px 10px;
}
.tag-pass { color: #0F6E56; }
.tag-fail { color: #8B3A32; font-weight: 500; }
.skipped-note { margin-top: -2px; font-size: 12px; }

.badge { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 100px; }
.badge--ok { background: #E1F5EE; color: #0F6E56; }
.badge--bad { background: #FBEEEC; color: #8B3A32; }

.image-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.image-grid figure {
  margin: 0; background: var(--surface); border: 1px solid var(--border-subtle);
  border-radius: 10px; overflow: hidden;
}
.image-grid img { width: 100%; aspect-ratio: 3 / 4; object-fit: cover; display: block; background: var(--bg-subtle); }
.image-grid figcaption { font-size: 11px; color: var(--text-muted); padding: 4px 7px; }
.ratio-tag { color: #0F6E56; margin-left: 4px; }

.shot { max-width: 680px; width: 100%; border: 1px solid var(--border-subtle); border-radius: 10px; display: block; }

.history { margin-top: 40px; }
.history-head { display: flex; justify-content: space-between; align-items: center; }
.history-head h4 { margin: 0 0 10px; }
.history-row { cursor: pointer; transition: background 0.12s; }
.history-row:hover { background: var(--bg-subtle); }

.muted { color: var(--text-muted); font-size: 13px; }

/* ── Tabs ── */
.tabs { display: flex; gap: 6px; margin-bottom: 20px; }
.tab {
  background: transparent; color: var(--text-muted);
  border: 1px solid transparent; padding: 6px 16px; font-size: 13px;
}
.tab:hover:not(:disabled) { background: var(--bg-subtle); color: var(--text); }
.tab--active {
  background: var(--surface); color: var(--text);
  border-color: var(--border); box-shadow: rgba(0,0,0,0.04) 0 2px 4px;
}

/* ── 店铺体检 ── */
.shop-view { max-width: 1000px; }
.shop-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.shop-head h3 { margin: 0 0 4px; font-size: 17px; font-weight: 500; color: var(--text); }
.meta-line { margin: 0; font-size: 12px; color: var(--text-muted); }

.metric-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 10px;
}
.metric {
  background: var(--surface); border-radius: 12px; padding: 12px 14px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px;
}
.metric-k { font-size: 11.5px; color: var(--text-muted); margin-bottom: 4px; }
.metric-v { font-size: 18px; font-weight: 500; color: var(--text); line-height: 1.3; }
.metric-sub { font-size: 11.5px; font-weight: 400; color: var(--text-muted); margin-left: 6px; }
.metric-v--bad { color: #8B3A32; }

.insight-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.insight {
  background: #F2F5F1; border-left: 2px solid #2F5D50; border-radius: 8px;
  padding: 11px 14px; font-size: 12.5px; line-height: 1.75; color: #2A4A40;
}
.insight b { display: block; font-weight: 500; margin-bottom: 2px; }

.footnote { margin-top: 10px; font-size: 12px; }

/* ── AI 解读 ── */
.ai-card {
  margin: 14px 0 22px; padding: 14px 16px;
  background: var(--surface); border-radius: 12px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px;
}
.ai-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.ai-head b { font-size: 14px; font-weight: 500; color: var(--text); }
.ai-sub { margin-left: 8px; font-size: 12px; color: var(--text-muted); }
.ai-placeholder { margin: 10px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--text-muted); }
.ai-error { margin: 10px 0 0; font-size: 12.5px; color: #8B3A32; }
.ai-headline {
  margin: 12px 0 10px; font-size: 14px; font-weight: 500; color: var(--text);
  line-height: 1.6;
}
.ai-findings { margin: 0; padding: 0; list-style: none; }
.ai-findings li {
  padding: 10px 0; border-top: 1px solid var(--border);
  font-size: 12.5px; line-height: 1.7; color: var(--text-secondary);
}
.ai-findings b { display: block; font-weight: 500; color: var(--text); margin-bottom: 2px; }
.ai-evidence { display: block; color: var(--text-muted); }
.ai-action { display: block; margin-top: 3px; color: #2F5D50; }
.ai-gap { margin: 10px 0 0; font-size: 12px; color: #8B3A32; line-height: 1.7; }
.ai-meta { margin: 8px 0 0; font-size: 11.5px; color: var(--text-muted); }

.ai-card--item { margin-top: 14px; }

/* ── 商品体检 ── */
.checkup { margin-top: 18px; }
.checkup-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.checkup-head h4 { margin: 0; }
.checkup-head .link-btn { padding: 2px 10px; font-size: 11.5px; }
.checkup-head .link-btn:disabled { opacity: 0.55; cursor: default; }
.checkup-verdict {
  font-size: 12px; padding: 2px 8px; border-radius: 9999px;
  background: #F2F5F1; color: #2F5D50; border: 1px solid #D7E3DD;
}
.checkup-verdict--bad { background: #FBF0EE; color: #8B3A32; border-color: #EFD9D4; }
.checkup-source {
  font-size: 11px; padding: 1px 7px; border-radius: 6px;
  background: var(--bg-subtle); color: var(--text-muted);
}
.checkup-source--llm { background: #EEF3F8; color: #3A5D7A; }
.checkup-note { font-size: 11.5px; color: var(--text-muted); }
.checkup-list { list-style: none; margin: 0; padding: 0; }
.checkup-row {
  display: flex; gap: 10px; padding: 10px 0;
  border-top: 1px solid var(--border); font-size: 12.5px; line-height: 1.7;
}
.checkup-tag {
  flex: 0 0 auto; align-self: flex-start; margin-top: 2px;
  font-size: 11px; padding: 1px 7px; border-radius: 6px; white-space: nowrap;
  background: var(--bg-subtle); color: var(--text-muted);
}
.checkup-row--bad .checkup-tag { background: #FBF0EE; color: #8B3A32; }
.checkup-row--warn .checkup-tag { background: #FBF6EC; color: #8B5A2B; }
.checkup-row--ok .checkup-tag { background: #F2F5F1; color: #2F5D50; }
.checkup-body b { display: block; font-weight: 500; color: var(--text); }
.checkup-problem { margin: 1px 0 0; color: var(--text-secondary); }
.checkup-impact { margin: 0; color: var(--text-muted); font-size: 12px; }
.checkup-action { margin: 3px 0 0; color: #2F5D50; }
.checkup-reason { margin: 3px 0 0; font-size: 11.5px; color: var(--text-muted); line-height: 1.6; }
.checkup-dismissed { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
.checkup-toggle {
  display: inline-flex; gap: 6px; align-items: baseline;
  padding: 0; border: 0; background: none; cursor: pointer;
  font-size: 12px; color: var(--text-muted);
}
.checkup-toggle:hover { color: var(--text-secondary); }
.checkup-toggle span { color: #3A5D7A; }
.checkup-dismissed-list { list-style: none; margin: 8px 0 0; padding: 0; }
.checkup-dismissed-list li {
  padding: 6px 0 6px 10px; border-left: 2px solid var(--border);
  font-size: 12px; line-height: 1.65; color: var(--text-secondary);
}
.checkup-dismissed-list b { display: block; font-weight: 500; color: var(--text-muted); }
.checkup-dismissed-list p { margin: 1px 0 0; }
.checkup-gaps { margin: 10px 0 0; font-size: 12px; color: var(--text-muted); line-height: 1.7; }
.ai-stage { display: flex; align-items: baseline; gap: 10px; margin: 12px 0 4px; flex-wrap: wrap; }
.ai-stage-tag {
  font-size: 11.5px; padding: 2px 8px; border-radius: 9999px;
  background: #F2F5F1; color: #2F5D50; border: 1px solid #D7E3DD;
  white-space: nowrap;
}
.ai-dont { margin: 10px 0 0; font-size: 12px; color: #8B5A2B; line-height: 1.7; }

/* AI 对话 */
.ai-chat { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }
.ai-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ai-chips-label {
  font-size: 11.5px; color: var(--text-muted); margin-right: 2px;
}
.ai-chip {
  padding: 4px 10px; font-size: 12px; border-radius: 9999px;
  background: var(--bg-subtle); color: var(--text-secondary);
  border: 1px solid var(--border); text-align: left;
}
.ai-chip:hover:not(:disabled) { border-color: #2F5D50; color: #2F5D50; }
.ai-chip:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-chat-log { max-height: 320px; overflow-y: auto; padding-right: 4px; }
.ai-msg { display: flex; gap: 8px; padding: 7px 0; font-size: 12.5px; line-height: 1.75; }
.ai-msg p { margin: 0; color: var(--text-secondary); white-space: pre-wrap; }
.ai-msg-role {
  flex: 0 0 22px; font-size: 11px; font-weight: 500; color: var(--text-muted);
  padding-top: 2px;
}
.ai-msg--user p { color: var(--text); }
.ai-msg--assistant .ai-msg-role { color: #2F5D50; }
.ai-typing { color: var(--text-muted); }
.ai-chat-input { display: flex; gap: 8px; align-items: center; margin-top: 10px; }
.ai-chat-input input {
  flex: 1; min-width: 0; padding: 8px 12px; font-size: 12.5px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-subtle); color: var(--text);
}
.ai-chat-input input:focus { outline: none; border-color: #2F5D50; }

/* ── 流量与转化 ── */
.section-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 36px; gap: 12px;
}
.section-head h4 { margin: 0 0 10px; }
.period-switch { display: flex; gap: 6px; margin-bottom: 10px; }
.period-btn {
  background: transparent; color: var(--text-muted);
  border: 1px solid var(--border); padding: 4px 12px; font-size: 12px;
}
.period-btn:hover:not(:disabled) { background: var(--bg-subtle); color: var(--text); }
.period-btn--active {
  background: #000; color: #fff; border-color: #000;
}
.period-btn--active:hover:not(:disabled) { background: #222; color: #fff; }
/* 未导入该周期的期次：仍可点击，点开给出明确说明，不能用置灰来藏住事实 */
.period-btn--missing:not(.period-btn--active) {
  border-style: dashed; color: var(--text-muted); opacity: 0.65;
}
.empty-note {
  background: var(--bg-subtle); border-radius: 10px; padding: 16px 18px;
  font-size: 13px; color: var(--text-muted); line-height: 1.7;
}
.traffic-body h4 { margin-top: 28px; }

/* ── 单商品流量诊断 ── */
.item-traffic { margin-bottom: 2px; }
.diagnosis {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
  padding: 11px 14px; border-radius: 8px; font-size: 12.5px;
  line-height: 1.75; margin-bottom: 12px;
}
.diag-label { font-weight: 500; white-space: nowrap; }
.diag-advice { opacity: 0.88; }
.diag--high_traffic_low_rate {
  background: #FBEEEC; color: #8B3A32; border-left: 2px solid #A8453A;
}
.diag--healthy {
  background: #E1F5EE; color: #0F6E56; border-left: 2px solid #0F6E56;
}
.diag--low_traffic_good_rate {
  background: #FAF3E8; color: #6B4A1E; border-left: 2px solid #B8762A;
}
.diag--no_traffic, .diag--low_both, .diag--low_sample {
  background: var(--bg-subtle); color: var(--text-muted);
  border-left: 2px solid var(--border);
}
.metric-grid--sm { grid-template-columns: repeat(auto-fit, minmax(126px, 1fr)); }
.bench { margin: 10px 0 0; font-size: 12px; line-height: 1.8; }
</style>
