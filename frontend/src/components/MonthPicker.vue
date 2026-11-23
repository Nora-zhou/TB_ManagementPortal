<script setup>
import { VueDatePicker } from '@vuepic/vue-datepicker'
import '@vuepic/vue-datepicker/dist/main.css'

defineProps({
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

function onUpdate(value) {
  if (!value) {
    emit('update:modelValue', '')
    return
  }
  if (value instanceof Date) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    emit('update:modelValue', `${year}-${month}`)
    return
  }
  emit('update:modelValue', String(value))
}
</script>

<template>
  <VueDatePicker
    :model-value="modelValue || null"
    month-picker
    auto-apply
    :text-input="false"
    :enable-time-picker="false"
    model-type="yyyy-MM"
    :formats="{ input: 'yyyy-MM', preview: 'yyyy-MM' }"
    :clearable="true"
    :teleport="true"
    placeholder="选择月份"
    class="month-picker"
    @update:model-value="onUpdate"
  />
</template>

<style scoped>
.month-picker {
  width: 150px;
}

.month-picker :deep(.dp--input) {
  padding: 7px 30px 7px 35px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  letter-spacing: 0.1px;
}

.month-picker :deep(.dp--input:focus) {
  border-color: var(--text-secondary);
}

.month-picker :deep(.dp--input-icon) {
  color: var(--text-muted);
}
</style>
