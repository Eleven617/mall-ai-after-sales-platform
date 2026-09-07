<script setup lang="ts">
import ServiceOperationsPanel from "./ServiceOperationsPanel.vue";
</script>

<template>
  <main class="internal-page-shell service-operations-page-shell">
    <section class="internal-page-product service-operations-page-product" aria-label="人工售后协同处理台">
      <header class="internal-page-topbar service-operations-page-topbar">
        <div class="internal-page-brand">
          <span class="internal-page-brand-mark" aria-hidden="true">AI</span>
          <div><p class="internal-page-product-name">Mall AI 售后平台</p><p class="internal-page-role">人工协同台 · 事实、证据与人工协同</p></div>
        </div>
        <div><h1>人工售后协同处理台</h1><p>领取、核验、处理和结案都保留服务端权限与审计边界。</p></div>
        <a href="/">返回客户咨询</a>
      </header>
      <ServiceOperationsPanel />
    </section>
  </main>
</template>

<style scoped>
@media (max-width: 900px) { .service-operations-page-topbar { display: grid; grid-template-columns: 1fr auto; } .service-operations-page-topbar > div:nth-child(2) { grid-column: 1 / -1; } }
@media (max-width: 520px) { .service-operations-page-shell { padding: 0; } .service-operations-page-product { min-height: 100vh; border: 0; border-radius: 0; } .service-operations-page-topbar { grid-template-columns: 1fr; align-items: flex-start; padding: 16px 18px; } .service-operations-page-topbar > div:nth-child(2) { grid-column: auto; } }
</style>
