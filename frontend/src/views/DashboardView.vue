<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import {
  fetchCategoryBreakdown,
  fetchComparison,
  fetchFixedVariable,
  fetchLargeTransactions,
  fetchMerchantRanking,
  fetchStatsSummary,
  fetchTrend,
} from '../api/stats'
import type {
  CategoryBreakdown,
  ComparisonResponse,
  FixedVariableBreakdown,
  LargeTransactionResponse,
  MerchantRanking,
  StatsSummary,
  TrendResponse,
} from '../types/stats'

const today = new Date()
const defaultFrom = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`
const defaultTo = [
  today.getFullYear(),
  String(today.getMonth() + 1).padStart(2, '0'),
  String(new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()).padStart(2, '0'),
].join('-')

const dateFrom = ref(defaultFrom)
const dateTo = ref(defaultTo)
const budgetYuan = ref('')
const busy = ref(false)
const error = ref('')

const summary = ref<StatsSummary | null>(null)
const categories = ref<CategoryBreakdown | null>(null)
const trend = ref<TrendResponse | null>(null)
const merchants = ref<MerchantRanking | null>(null)
const largeTransactions = ref<LargeTransactionResponse | null>(null)
const fixedVariable = ref<FixedVariableBreakdown | null>(null)
const comparison = ref<ComparisonResponse | null>(null)
const trendChartElement = ref<HTMLElement | null>(null)
const categoryChartElement = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
let categoryChart: echarts.ECharts | null = null

const formatter = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const maxCategoryAmount = computed(() =>
  Math.max(1, ...((categories.value?.items ?? []).map((item) => item.amount_minor))),
)
const maxMerchantAmount = computed(() =>
  Math.max(1, ...((merchants.value?.items ?? []).map((item) => item.amount_minor))),
)

function money(value: number | undefined, currency?: string): string {
  return `${formatter.format((value ?? 0) / 100)} ${currency || summary.value?.currency || 'CNY'}`
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function budgetMinor(): number | undefined {
  const normalized = budgetYuan.value.trim()
  if (!normalized) return undefined
  const match = /^(\d+)(?:\.(\d{0,2}))?$/.exec(normalized)
  if (!match) {
    throw new Error('预算请输入非负数字，单位是元')
  }
  const whole = Number(match[1])
  const fraction = Number((match[2] || '').padEnd(2, '0'))
  const result = whole * 100 + fraction
  if (!Number.isSafeInteger(result)) {
    throw new Error('预算金额过大')
  }
  return result
}

function query() {
  return {
    from: dateFrom.value || undefined,
    to: dateTo.value || undefined,
  }
}

async function refresh() {
  busy.value = true
  error.value = ''
  try {
    const currentQuery = query()
    const currentBudget = budgetMinor()
    const [
      summaryResult,
      categoriesResult,
      trendResult,
      merchantsResult,
      largeResult,
      fixedResult,
      comparisonResult,
    ] = await Promise.all([
      fetchStatsSummary(currentQuery, currentBudget),
      fetchCategoryBreakdown(currentQuery, 'expense'),
      fetchTrend(currentQuery, 'day'),
      fetchMerchantRanking(currentQuery, 'expense', 8),
      fetchLargeTransactions(currentQuery, 10_000, 10, 'expense'),
      fetchFixedVariable(currentQuery),
      fetchComparison(currentQuery, 'previous'),
    ])
    summary.value = summaryResult
    categories.value = categoriesResult
    trend.value = trendResult
    merchants.value = merchantsResult
    largeTransactions.value = largeResult
    fixedVariable.value = fixedResult
    comparison.value = comparisonResult
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取统计数据'
  } finally {
    busy.value = false
  }
}

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString()
}

function disposeCharts(): void {
  trendChart?.dispose()
  categoryChart?.dispose()
  trendChart = null
  categoryChart = null
}

function renderCharts(): void {
  const trendData = trend.value
  const categoryData = categories.value

  if (trendChartElement.value && trendData && trendData.items.length) {
    trendChart?.dispose()
    trendChart = echarts.init(trendChartElement.value, undefined, {
      renderer: 'svg',
      width: trendChartElement.value.clientWidth || 640,
      height: 280,
    })
    trendChart.setOption({
      animation: false,
      grid: { left: 56, right: 24, top: 18, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number) =>
          `${(value / 100).toFixed(2)} ${trendData.currency}`,
      },
      xAxis: {
        type: 'category',
        data: trendData.items.map((item) => item.label),
        axisLabel: { rotate: trendData.items.length > 14 ? 35 : 0 },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: (value: number) => `${(value / 100).toFixed(0)}`,
        },
      },
      series: [
        {
          name: '支出',
          type: 'bar',
          data: trendData.items.map((item) => item.expense_minor),
          itemStyle: { color: '#ef4444', borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 28,
        },
      ],
    })
  } else {
    trendChart?.dispose()
    trendChart = null
  }

  if (categoryChartElement.value && categoryData && categoryData.items.length) {
    categoryChart?.dispose()
    categoryChart = echarts.init(categoryChartElement.value, undefined, {
      renderer: 'svg',
      width: categoryChartElement.value.clientWidth || 480,
      height: 280,
    })
    categoryChart.setOption({
      animation: false,
      tooltip: {
        trigger: 'item',
        valueFormatter: (value: number) =>
          `${(value / 100).toFixed(2)} ${categoryData.currency}`,
      },
      legend: { type: 'scroll', bottom: 0 },
      series: [
        {
          name: '支出类别',
          type: 'pie',
          radius: ['38%', '68%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          data: categoryData.items.slice(0, 8).map((item) => ({
            name: item.category,
            value: item.amount_minor,
          })),
        },
      ],
    })
  } else {
    categoryChart?.dispose()
    categoryChart = null
  }
}

function resizeCharts(): void {
  trendChart?.resize()
  categoryChart?.resize()
}

watch([trend, categories], () => {
  void nextTick(renderCharts)
})

onMounted(async () => {
  await refresh()
  await nextTick(renderCharts)
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  disposeCharts()
})
</script>

<template>
  <main class="dashboard-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">DASHBOARD</p>
        <h1>消费 Dashboard</h1>
        <p class="muted">
          页面只消费后端统计 API；退款、转账、失败交易和时间边界按阶段 3 口径统一计算。
        </p>
      </div>
    </header>

    <form class="filters" @submit.prevent="refresh">
      <label>
        <span>开始日期</span>
        <input v-model="dateFrom" type="date" aria-label="开始日期">
      </label>
      <label>
        <span>结束日期</span>
        <input v-model="dateTo" type="date" aria-label="结束日期">
      </label>
      <label>
        <span>预算（元，可选）</span>
        <input v-model="budgetYuan" inputmode="decimal" placeholder="例如 5000">
      </label>
      <button type="submit" :disabled="busy">{{ busy ? '刷新中…' : '刷新统计' }}</button>
    </form>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <section v-if="summary" class="summary-grid" aria-label="汇总指标">
      <article class="metric-card expense">
        <span>支出</span>
        <strong>{{ money(summary.expense_minor, summary.currency) }}</strong>
        <small>{{ summary.expense_count }} 笔</small>
      </article>
      <article class="metric-card income">
        <span>收入</span>
        <strong>{{ money(summary.income_minor, summary.currency) }}</strong>
        <small>含退款 {{ money(summary.refund_minor, summary.currency) }}</small>
      </article>
      <article class="metric-card" :class="{ income: summary.net_flow_minor >= 0, expense: summary.net_flow_minor < 0 }">
        <span>净流量</span>
        <strong>{{ money(summary.net_flow_minor, summary.currency) }}</strong>
        <small>收入 - 支出</small>
      </article>
      <article class="metric-card">
        <span>有效交易</span>
        <strong>{{ summary.transaction_count }}</strong>
        <small>转账 {{ summary.transfer_count }} · 排除 {{ summary.excluded_count }}</small>
      </article>
    </section>

    <section v-if="summary?.budget" class="panel budget-panel" aria-labelledby="budget-title">
      <div>
        <p class="eyebrow">BUDGET</p>
        <h2 id="budget-title">预算状态</h2>
      </div>
      <div class="budget-grid">
        <div><span>预算</span><strong>{{ money(summary.budget.budget_minor, summary.currency) }}</strong></div>
        <div><span>已用</span><strong>{{ money(summary.budget.used_minor, summary.currency) }}</strong></div>
        <div><span>剩余</span><strong>{{ money(summary.budget.remaining_minor, summary.currency) }}</strong></div>
        <div><span>超支</span><strong>{{ money(summary.budget.over_budget_minor, summary.currency) }}</strong></div>
      </div>
      <div class="progress-track" aria-label="预算使用率">
        <div
          class="progress-fill"
          :class="{ over: summary.budget.over_budget_minor > 0 }"
          :style="{ width: `${Math.min(summary.budget.utilization_percent, 100)}%` }"
        />
      </div>
      <p class="muted">使用率 {{ summary.budget.utilization_percent.toFixed(2) }}%</p>
    </section>

    <section class="dashboard-grid">
      <article class="panel wide" aria-labelledby="trend-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">TREND</p>
            <h2 id="trend-title">每日支出趋势</h2>
          </div>
          <span class="muted">{{ trend?.items.length || 0 }} 个时间桶</span>
        </div>
        <div
          v-if="trend?.items.length"
          ref="trendChartElement"
          class="chart chart-trend"
          aria-label="每日支出趋势图"
        />
        <div v-if="trend?.items.length" class="chart-summary">
          <span>金额由后端以最小单位传输，坐标轴显示元</span>
          <span>趋势数据来自后端 Stats Service</span>
        </div>
        <p v-else class="muted empty">当前周期没有趋势数据。</p>
      </article>

      <article class="panel" aria-labelledby="category-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">CATEGORY</p>
            <h2 id="category-title">支出类别构成</h2>
          </div>
        </div>
        <div
          v-if="categories?.items.length"
          ref="categoryChartElement"
          class="chart chart-category"
          aria-label="支出类别构成图"
        />
        <div v-if="categories?.items.length" class="rank-list">
          <div v-for="item in categories.items.slice(0, 8)" :key="item.category" class="rank-row">
            <div>
              <strong>{{ item.category }}</strong>
              <p>{{ item.transaction_count }} 笔 · {{ item.share_percent.toFixed(2) }}%</p>
            </div>
            <span>{{ money(item.amount_minor, categories.currency) }}</span>
            <div class="mini-track">
              <div class="mini-fill" :style="{ width: `${(item.amount_minor / maxCategoryAmount) * 100}%` }" />
            </div>
          </div>
        </div>
        <p v-else class="muted empty">还没有支出分类。</p>
      </article>

      <article class="panel" aria-labelledby="merchant-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">MERCHANT</p>
            <h2 id="merchant-title">商户排行</h2>
          </div>
        </div>
        <div v-if="merchants?.items.length" class="rank-list">
          <RouterLink
            v-for="item in merchants.items"
            :key="item.merchant"
            class="rank-row drill-link"
            :to="{ path: '/transactions', query: { merchant: item.merchant } }"
          >
            <div>
              <strong>{{ item.merchant }}</strong>
              <p>{{ item.transaction_count }} 笔 · {{ item.share_percent.toFixed(2) }}%</p>
            </div>
            <span>{{ money(item.amount_minor, merchants.currency) }}</span>
            <div class="mini-track">
              <div class="mini-fill" :style="{ width: `${(item.amount_minor / maxMerchantAmount) * 100}%` }" />
            </div>
          </RouterLink>
        </div>
        <p v-else class="muted empty">还没有商户排行。</p>
      </article>

      <article class="panel" aria-labelledby="fixed-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">FIXED / VARIABLE</p>
            <h2 id="fixed-title">固定与可变支出</h2>
          </div>
        </div>
        <div v-if="fixedVariable" class="split-grid">
          <div>
            <span>固定支出</span>
            <strong>{{ money(fixedVariable.fixed_minor, fixedVariable.currency) }}</strong>
            <small>{{ fixedVariable.fixed_count }} 笔</small>
          </div>
          <div>
            <span>可变支出</span>
            <strong>{{ money(fixedVariable.variable_minor, fixedVariable.currency) }}</strong>
            <small>{{ fixedVariable.variable_count }} 笔</small>
          </div>
        </div>
      </article>

      <article class="panel" aria-labelledby="comparison-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">COMPARISON</p>
            <h2 id="comparison-title">环比变化</h2>
          </div>
        </div>
        <dl v-if="comparison" class="comparison-list">
          <div>
            <dt>支出变化</dt>
            <dd>{{ money(comparison.metrics.expense_minor?.delta, comparison.current.currency) }}</dd>
            <small>{{ percent(comparison.metrics.expense_minor?.delta_percent) }}</small>
          </div>
          <div>
            <dt>收入变化</dt>
            <dd>{{ money(comparison.metrics.income_minor?.delta, comparison.current.currency) }}</dd>
            <small>{{ percent(comparison.metrics.income_minor?.delta_percent) }}</small>
          </div>
          <div>
            <dt>净流量变化</dt>
            <dd>{{ money(comparison.metrics.net_flow_minor?.delta, comparison.current.currency) }}</dd>
            <small>{{ percent(comparison.metrics.net_flow_minor?.delta_percent) }}</small>
          </div>
        </dl>
      </article>

      <article class="panel wide" aria-labelledby="large-title">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">LARGE TRANSACTIONS</p>
            <h2 id="large-title">大额支出</h2>
          </div>
          <span class="muted">默认阈值 {{ money(largeTransactions?.threshold_minor, largeTransactions?.currency) }}</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>日期</th><th>商户</th><th>描述</th><th>分类</th><th>金额</th><th /></tr>
            </thead>
            <tbody>
              <tr v-for="item in largeTransactions?.items || []" :key="item.id">
                <td>{{ dateLabel(item.occurred_at) }}</td>
                <td>{{ item.merchant || '—' }}</td>
                <td>{{ item.description || '—' }}</td>
                <td>{{ item.category || '未分类' }}</td>
                <td class="expense">{{ money(item.amount_minor, item.currency) }}</td>
                <td>
                  <RouterLink class="link-button" :to="{ path: '/transactions', query: { merchant: item.merchant } }">
                    下钻
                  </RouterLink>
                </td>
              </tr>
              <tr v-if="!largeTransactions?.items.length">
                <td colspan="6" class="muted empty">没有超过阈值的大额支出。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.dashboard-page { max-width: 1200px; margin: 0 auto; padding: 40px 24px; }
.page-heading { margin-bottom: 22px; }
h1 { margin: 8px 0; font-size: 40px; }
h2 { margin: 4px 0 0; font-size: 20px; }
.eyebrow { color: #64748b; letter-spacing: .12em; font-size: 12px; text-transform: uppercase; }
.muted { color: #64748b; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 18px; padding: 16px; border: 1px solid #e5e7eb; border-radius: 16px; background: white; }
.filters label { display: flex; flex-direction: column; gap: 6px; color: #475569; font-size: 13px; }
input { border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 12px; min-width: 150px; }
button { border: 0; border-radius: 8px; padding: 11px 18px; background: #2563eb; color: white; cursor: pointer; font-weight: 600; }
button:disabled { opacity: .6; cursor: wait; }
.error { color: #b91c1c; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 18px 0; }
.metric-card, .panel { background: white; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 10px 30px rgb(15 23 42 / 5%); }
.metric-card { padding: 18px; display: flex; flex-direction: column; gap: 8px; }
.metric-card span, .budget-grid span, .split-grid span { color: #64748b; font-size: 13px; }
.metric-card strong { color: #0f172a; font-size: 24px; }
.metric-card.expense strong, .expense { color: #b91c1c; }
.metric-card.income strong, .income { color: #15803d; }
.metric-card small, .split-grid small { color: #64748b; }
.panel { padding: 20px; }
.budget-panel { margin-bottom: 18px; }
.dashboard-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.wide { grid-column: 1 / -1; }
.panel-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.budget-grid, .split-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.budget-grid div, .split-grid div { padding: 14px; border-radius: 12px; background: #f8fafc; display: flex; flex-direction: column; gap: 6px; }
.progress-track, .mini-track { overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.progress-track { height: 10px; margin-top: 16px; }
.progress-fill, .mini-fill { height: 100%; border-radius: inherit; transition: width .2s ease; }
.progress-fill, .mini-fill { background: #2563eb; }
.progress-fill.over { background: #ef4444; }
.chart { width: 100%; height: 280px; }
.chart-summary { display: flex; justify-content: space-between; gap: 12px; color: #64748b; font-size: 12px; }
.rank-list { display: grid; gap: 12px; }
.rank-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 12px; align-items: center; color: inherit; text-decoration: none; }
.rank-row p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.mini-track { grid-column: 1 / -1; height: 7px; }
.drill-link:hover strong { color: #2563eb; }
.comparison-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 0; }
.comparison-list div { padding: 14px; background: #f8fafc; border-radius: 12px; }
.comparison-list dt { color: #64748b; font-size: 12px; }
.comparison-list dd { margin: 6px 0 3px; font-weight: 700; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 760px; }
th, td { padding: 12px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; font-size: 14px; }
th { color: #64748b; font-weight: 600; }
.link-button { color: #2563eb; text-decoration: none; }
.empty { text-align: center; padding: 28px; }
@media (max-width: 800px) {
  .dashboard-grid { grid-template-columns: 1fr; }
}
</style>
