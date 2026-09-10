<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchTransaction, fetchTransactions, updateTransactionCategory } from '../api/finance'
import type { Transaction } from '../types/finance'

const transactions = ref<Transaction[]>([])
const merchant = ref('')
const category = ref('')
const error = ref('')
const selected = ref<Transaction | null>(null)

async function refresh() {
  try {
    const result = await fetchTransactions({ merchant: merchant.value, category: category.value })
    transactions.value = result.items
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取交易'
  }
}

async function editCategory(item: Transaction) {
  const value = window.prompt('输入分类（留空可清除）', item.category || '')
  if (value === null) return
  try {
    const updated = await updateTransactionCategory(item.id, value.trim() || null)
    Object.assign(item, updated)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '分类修改失败'
  }
}

async function showDetails(item: Transaction) {
  try {
    selected.value = await fetchTransaction(item.id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取交易详情'
  }
}

onMounted(refresh)
</script>

<template>
  <main class="finance-page">
    <header class="page-heading">
      <div><p class="eyebrow">TRANSACTIONS</p><h1>交易管理</h1><p class="muted">所有金额来自后端确定性结果；分类修改会记录来源。</p></div>
    </header>
    <form class="filters" @submit.prevent="refresh">
      <input v-model="merchant" aria-label="商户" placeholder="搜索商户">
      <input v-model="category" aria-label="分类" placeholder="分类">
      <button type="submit">筛选</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <section class="panel table-wrap">
      <table>
        <thead><tr><th>时间</th><th>商户</th><th>描述</th><th>方向</th><th>金额</th><th>分类</th><th /></tr></thead>
        <tbody>
          <tr v-for="item in transactions" :key="item.id">
            <td>{{ new Date(item.occurred_at).toLocaleString() }}</td>
            <td>{{ item.merchant || '—' }}</td>
            <td>{{ item.description || '—' }}</td>
            <td>{{ item.direction }}</td>
            <td :class="item.direction === 'expense' ? 'expense' : 'income'">{{ (item.amount_minor / 100).toFixed(2) }} {{ item.currency }}</td>
            <td>{{ item.category || '未分类' }}</td>
            <td class="actions"><button class="link-button" @click="showDetails(item)">详情</button><button class="link-button" @click="editCategory(item)">修改</button></td>
          </tr>
          <tr v-if="!transactions.length"><td colspan="7" class="muted empty">暂无交易</td></tr>
        </tbody>
      </table>
    </section>
    <section v-if="selected" class="panel detail-panel" aria-labelledby="detail-title">
      <div class="detail-heading"><h2 id="detail-title">交易详情</h2><button class="link-button" @click="selected = null">关闭</button></div>
      <dl class="details">
        <div><dt>交易 ID</dt><dd>{{ selected.id }}</dd></div>
        <div><dt>导入任务</dt><dd>{{ selected.bill_import_id }}</dd></div>
        <div><dt>来源流水号</dt><dd>{{ selected.source_transaction_id || '—' }}</dd></div>
        <div><dt>支付方式</dt><dd>{{ selected.payment_method || '—' }}</dd></div>
        <div><dt>平台分类</dt><dd>{{ selected.platform_category || '—' }}</dd></div>
        <div><dt>分类来源</dt><dd>{{ selected.category_source || '未分类' }}</dd></div>
      </dl>
    </section>
  </main>
</template>

<style scoped>
.finance-page { max-width: 1200px; margin: 0 auto; padding: 40px 24px; }
.page-heading { margin-bottom: 24px; } h1 { margin: 8px 0; font-size: 40px; }
.eyebrow { color: #64748b; letter-spacing: .12em; font-size: 12px; } .muted { color: #64748b; }
.filters { display: flex; gap: 10px; margin-bottom: 18px; } input { border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 12px; } button { border: 0; border-radius: 8px; padding: 10px 16px; background: #2563eb; color: white; cursor: pointer; }
.panel { padding: 8px 20px; background: white; border: 1px solid #e5e7eb; border-radius: 16px; } .table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 760px; } th, td { text-align: left; padding: 13px 8px; border-bottom: 1px solid #f1f5f9; font-size: 14px; } th { color: #64748b; font-weight: 600; }
.expense { color: #b91c1c; } .income { color: #15803d; } .link-button { background: none; color: #2563eb; padding: 4px 8px; } .actions { white-space: nowrap; } .empty { text-align: center; padding: 30px; } .error { color: #b91c1c; }
.detail-panel { margin-top: 18px; } .detail-heading { display: flex; align-items: center; justify-content: space-between; } .details { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; } .details div { padding: 12px; background: #f8fafc; border-radius: 8px; } dt { color: #64748b; font-size: 12px; } dd { margin: 5px 0 0; word-break: break-word; }
@media (max-width: 600px) { .filters { flex-direction: column; } }
</style>
