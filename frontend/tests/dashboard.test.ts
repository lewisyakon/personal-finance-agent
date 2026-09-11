// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import DashboardView from '../src/views/DashboardView.vue'

vi.mock('../src/api/stats', () => ({
  fetchStatsSummary: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    transaction_count: 3,
    expense_count: 2,
    income_count: 1,
    transfer_count: 0,
    refund_count: 0,
    excluded_count: 0,
    expense_minor: 12345,
    income_minor: 20000,
    refund_minor: 0,
    net_flow_minor: 7655,
    fixed_expense_count: 1,
    variable_expense_count: 1,
    fixed_expense_minor: 5000,
    variable_expense_minor: 7345,
    budget: {
      budget_minor: 20000,
      used_minor: 12345,
      remaining_minor: 7655,
      over_budget_minor: 0,
      utilization_percent: 61.73,
    },
  }),
  fetchCategoryBreakdown: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    direction: 'expense',
    items: [
      {
        category: '餐饮/午餐',
        primary_category: '餐饮',
        secondary_category: '午餐',
        amount_minor: 12345,
        transaction_count: 2,
        share_percent: 100,
      },
    ],
  }),
  fetchTrend: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    granularity: 'day',
    items: [
      {
        bucket_start: '2026-01-03T00:00:00+08:00',
        bucket_end: '2026-01-04T00:00:00+08:00',
        label: '2026-01-03',
        transaction_count: 1,
        expense_count: 1,
        income_count: 0,
        transfer_count: 0,
        refund_count: 0,
        expense_minor: 12345,
        income_minor: 0,
        refund_minor: 0,
        net_flow_minor: -12345,
        fixed_expense_minor: 0,
        variable_expense_minor: 12345,
      },
    ],
  }),
  fetchMerchantRanking: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    direction: 'expense',
    items: [{ merchant: '示例商户', amount_minor: 12345, transaction_count: 1, share_percent: 100 }],
  }),
  fetchLargeTransactions: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    direction: 'expense',
    threshold_minor: 10000,
    items: [
      {
        id: 1,
        occurred_at: '2026-01-03T10:00:00+08:00',
        merchant: '示例商户',
        description: '示例消费',
        direction: 'expense',
        amount_minor: 12345,
        currency: 'CNY',
        status: 'success',
        category: '餐饮/午餐',
      },
    ],
  }),
  fetchFixedVariable: vi.fn().mockResolvedValue({
    period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
    currency: 'CNY',
    fixed_count: 1,
    variable_count: 1,
    fixed_minor: 5000,
    variable_minor: 7345,
  }),
  fetchComparison: vi.fn().mockResolvedValue({
    current: {
      period: { start: '2026-01-01T00:00:00+08:00', end: '2026-02-01T00:00:00+08:00', timezone: 'Asia/Shanghai' },
      currency: 'CNY',
    },
    comparison: {},
    comparison_mode: 'previous',
    metrics: {
      expense_minor: { current: 12345, comparison: 10000, delta: 2345, delta_percent: 23.45 },
      income_minor: { current: 20000, comparison: 10000, delta: 10000, delta_percent: 100 },
      net_flow_minor: { current: 7655, comparison: 0, delta: 7655, delta_percent: null },
    },
  }),
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
  })),
}))

describe('stage 3 dashboard', () => {
  it('renders backend-provided statistics and drill-down links', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/dashboard', component: DashboardView },
        { path: '/transactions', component: DashboardView },
      ],
    })
    await router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DashboardView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('123.45 CNY')
    expect(wrapper.text()).toContain('示例商户')
    expect(wrapper.text()).toContain('预算状态')
    expect(wrapper.find('.chart-trend').exists()).toBe(true)
    expect(wrapper.find('.chart-category').exists()).toBe(true)
    const links = wrapper.findAll('a').map((link) => link.attributes('href') || '')
    expect(links.some((href) => href.startsWith('/transactions?merchant='))).toBe(true)
  })
})
