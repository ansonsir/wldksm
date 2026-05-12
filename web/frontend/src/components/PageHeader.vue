<template>
  <div class="page-header">
    <div class="page-header-left">
      <h2>
        <el-icon v-if="icon" class="header-icon" :size="20"><component :is="icon" /></el-icon>
        {{ title }}
      </h2>
      <p v-if="subtitle" class="header-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.extra" class="page-header-right">
      <slot name="extra" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  icon: { type: [String, Object], default: null },
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--neutral-border);
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--neutral-text-dark);
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-icon {
  color: var(--brand-primary);
}
.header-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--neutral-text-light);
}
.page-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
