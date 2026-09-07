<script setup lang="ts">
import QualityPanel from "./QualityPanel.vue";
</script>

<template>
  <main class="internal-page-shell quality-page-shell">
    <section class="internal-page-product quality-page-product" aria-label="AI 质量开发者工作台">
      <header class="internal-page-topbar quality-page-topbar">
        <div class="internal-page-brand">
          <span class="internal-page-brand-mark" aria-hidden="true">AI</span>
          <div><p class="internal-page-product-name">Mall AI 售后平台</p><p class="internal-page-role">质量评测台 · 事实、证据与人工协同</p></div>
        </div>
        <div><h1>AI 质量开发者工作台</h1><p>版本化合同、合成评测与人工审核共同守住质量边界。</p></div>
        <a href="/">返回客户咨询</a>
      </header>
      <QualityPanel />
    </section>
  </main>
</template>

<style scoped>
@media (max-width: 900px) { .quality-page-topbar { display: grid; grid-template-columns: 1fr auto; } .quality-page-topbar > div:nth-child(2) { grid-column: 1 / -1; } }
@media (max-width: 520px) { .quality-page-shell { padding: 0; } .quality-page-product { min-height: 100vh; border: 0; border-radius: 0; } .quality-page-topbar { grid-template-columns: 1fr; align-items: flex-start; padding: 16px 18px; } .quality-page-topbar > div:nth-child(2) { grid-column: auto; } }
</style>
