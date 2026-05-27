<script setup>
const props = defineProps({
  task: { type: Object, required: true },
})

const emit = defineEmits(['update-status', 'delete'])

const STATUS_CYCLE = { todo: 'in_progress', in_progress: 'done', done: 'todo' }
const STATUS_LABEL = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' }
const PRIORITY_LABEL = { low: 'Low', medium: 'Med', high: 'High' }

function cycleStatus() {
  emit('update-status', props.task.id, STATUS_CYCLE[props.task.status])
}

function requestDelete() {
  if (window.confirm(`Delete task "${props.task.title}"?`)) {
    emit('delete', props.task.id)
  }
}
</script>

<template>
  <div class="task-item" :class="`status-${task.status}`">
    <div class="task-main">
      <span class="task-title" :class="{ strikethrough: task.status === 'done' }">
        {{ task.title }}
      </span>
      <p v-if="task.description" class="task-desc">{{ task.description }}</p>
    </div>
    <div class="task-actions">
      <span class="badge" :class="`priority-${task.priority}`">
        {{ PRIORITY_LABEL[task.priority] }}
      </span>
      <button class="btn btn-status" :class="`status-btn-${task.status}`" @click="cycleStatus">
        {{ STATUS_LABEL[task.status] }}
      </button>
      <button class="btn btn-danger" @click="requestDelete">✕</button>
    </div>
  </div>
</template>
