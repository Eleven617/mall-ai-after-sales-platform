<script setup lang="ts">
import OperationsPanel from "./OperationsPanel.vue";
</script>

<template>
  <main class="internal-page-shell operations-page-shell">
    <section class="internal-page-product operations-page-product" aria-label="售后运营工作台">
      <header class="internal-page-topbar operations-page-topbar">
        <div class="internal-page-brand">
          <span class="internal-page-brand-mark" aria-hidden="true">AI</span>
          <div>
            <p class="internal-page-product-name">Mall AI 售后平台</p>
            <p class="internal-page-role">运营工作台 · 事实、证据与人工协同</p>
          </div>
        </div>
        <div>
          <h1>售后运营工作台</h1>
          <p>用可信聚合数据观察转人工事项，不直接修改订单或售后。</p>
        </div>
        <a href="/">返回客户咨询</a>
      </header>
      <OperationsPanel />
    </section>
  </main>
</template>

<style scoped>
@media (max-width: 900px) { .operations-page-topbar { display: grid; grid-template-columns: 1fr auto; } .operations-page-topbar > div:nth-child(2) { grid-column: 1 / -1; } }
@media (max-width: 520px) { .operations-page-shell { padding: 0; } .operations-page-product { min-height: 100vh; border: 0; border-radius: 0; } .operations-page-topbar { grid-template-columns: 1fr; align-items: flex-start; padding: 16px 18px; } .operations-page-topbar > div:nth-child(2) { grid-column: auto; } }
</style>
