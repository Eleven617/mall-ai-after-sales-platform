<script setup lang="ts">
import QualityPanel from "./QualityPanel.vue";
</script>

<template>
  <main class="quality-page-shell">
    <section class="quality-page-product" aria-label="AI 质量开发者工作台">
      <header class="quality-page-topbar">
        <div>
          <p>INTERNAL QUALITY</p>
          <h1>AI 质量开发者工作台</h1>
        </div>
        <a href="/">返回客户咨询</a>
      </header>
      <QualityPanel />
    </section>
  </main>
</template>

<style scoped>
.quality-page-shell { min-height: 100vh; padding: 32px; background: #eff6ff; }
.quality-page-product { width: min(1180px, 100%); min-height: calc(100vh - 64px); margin: 0 auto; overflow: hidden; border: 1px solid #dbe5ee; border-radius: 24px; background: #fff; box-shadow: 0 18px 50px rgb(15 23 42 / 10%); }
.quality-page-topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 84px; padding: 18px 28px; border-bottom: 1px solid #e7edf3; }
.quality-page-topbar p { margin: 0; color: #0f766e; font-size: 11px; font-weight: 800; letter-spacing: .09em; }
.quality-page-topbar h1 { margin: 5px 0 0; color: #1e293b; font-size: 20px; }
.quality-page-topbar a { color: #2563eb; font-size: 13px; font-weight: 700; text-decoration: none; }
@media (max-width: 780px) { .quality-page-shell { padding: 0; } .quality-page-product { min-height: 100vh; border: 0; border-radius: 0; } .quality-page-topbar { align-items: flex-start; padding: 16px 18px; } }
</style>
