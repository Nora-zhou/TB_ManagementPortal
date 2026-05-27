<script setup>
import { ref } from 'vue'

const props = defineProps({
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['submit'])

const title = ref('')
const description = ref('')
const priority = ref('medium')
const titleError = ref('')

function submit() {
  titleError.value = ''
  if (!title.value.trim()) {
    titleError.value = 'Title is required.'
    return
  }
  emit('submit', {
    title: title.value.trim(),
    description: description.value.trim() || null,
    priority: priority.value,
  })
  title.value = ''
  description.value = ''
  priority.value = 'medium'
}
</script>

<template>
  <form class="task-form" @submit.prevent="submit">
    <div class="form-row">
      <input
        v-model="title"
        class="input"
        :class="{ error: titleError }"
        placeholder="New task title…"
        maxlength="200"
      />
      <select v-model="priority" class="select">
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
      </select>
      <button type="submit" class="btn btn-primary" :disabled="loading">
        {{ loading ? 'Adding…' : 'Add Task' }}
      </button>
    </div>
    <input
      v-model="description"
      class="input"
      placeholder="Description (optional)"
      maxlength="1000"
      style="margin-top: 6px"
    />
    <p v-if="titleError" class="form-error">{{ titleError }}</p>
  </form>
</template>
