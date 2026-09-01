<script setup lang="ts">
import ServiceOperationsPanel from "./ServiceOperationsPanel.vue";
</script>

<template>
  <main class="service-operations-page-shell">
    <section class="service-operations-page-product" aria-label="人工售后协同处理台">
      <header class="service-operations-page-topbar"><div><p>INTERNAL SERVICE OPERATIONS</p><h1>人工售后协同处理台</h1></div><a href="/">返回客户咨询</a></header>
      <ServiceOperationsPanel />
    </section>
  </main>
</template>

<style scoped>
.service-operations-page-shell { min-height: 100vh; padding: 32px; background: #fff7ed; }.service-operations-page-product { width: min(1220px, 100%); min-height: calc(100vh - 64px); margin: 0 auto; overflow: hidden; border: 1px solid #fed7aa; border-radius: 24px; background: #fff; box-shadow: 0 18px 50px rgb(124 45 18 / 10%); }.service-operations-page-topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 84px; padding: 18px 28px; border-bottom: 1px solid #fed7aa; }.service-operations-page-topbar p { margin: 0; color: #c2410c; font-size: 11px; font-weight: 800; letter-spacing: .09em; }.service-operations-page-topbar h1 { margin: 5px 0 0; color: #7c2d12; font-size: 20px; }.service-operations-page-topbar a { color: #c2410c; font-size: 13px; font-weight: 700; text-decoration: none; }@media (max-width: 780px) { .service-operations-page-shell { padding: 0; }.service-operations-page-product { min-height: 100vh; border: 0; border-radius: 0; }.service-operations-page-topbar { align-items: flex-start; padding: 16px 18px; } }
</style>
