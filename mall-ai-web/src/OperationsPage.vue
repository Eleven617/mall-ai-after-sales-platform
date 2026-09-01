<script setup lang="ts">
import OperationsPanel from "./OperationsPanel.vue";
</script>

<template>
  <main class="operations-page-shell">
    <section class="operations-page-product" aria-label="售后运营工作台">
      <header class="operations-page-topbar">
        <div>
          <p>INTERNAL OPERATIONS</p>
          <h1>售后运营工作台</h1>
        </div>
        <a href="/">返回客户咨询</a>
      </header>
      <OperationsPanel />
    </section>
  </main>
</template>

<style scoped>
.operations-page-shell { min-height: 100vh; padding: 32px; background: #eef3f8; }
.operations-page-product { width: min(1220px, 100%); min-height: calc(100vh - 64px); margin: 0 auto; overflow: hidden; border: 1px solid #dbe5ee; border-radius: 24px; background: #fff; box-shadow: 0 18px 50px rgb(15 23 42 / 10%); }
.operations-page-topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 84px; padding: 18px 28px; border-bottom: 1px solid #e7edf3; }
.operations-page-topbar p { margin: 0; color: #0f766e; font-size: 11px; font-weight: 800; letter-spacing: .09em; }
.operations-page-topbar h1 { margin: 5px 0 0; color: #1e293b; font-size: 20px; }
.operations-page-topbar a { color: #2563eb; font-size: 13px; font-weight: 700; text-decoration: none; }
@media (max-width: 780px) { .operations-page-shell { padding: 0; } .operations-page-product { min-height: 100vh; border: 0; border-radius: 0; } .operations-page-topbar { align-items: flex-start; padding: 16px 18px; } }
</style>
