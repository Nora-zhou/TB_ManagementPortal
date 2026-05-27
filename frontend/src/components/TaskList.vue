<script setup>
import TaskItem from './TaskItem.vue'

defineProps({
  tasks: { type: Array, required: true },
})

const emit = defineEmits(['update-status', 'delete'])
</script>

<template>
  <div class="task-list">
    <p v-if="tasks.length === 0" class="empty-state">
      No tasks yet — add one above!
    </p>
    <TaskItem
      v-for="task in tasks"
      :key="task.id"
      :task="task"
      @update-status="(id, status) => emit('update-status', id, status)"
      @delete="(id) => emit('delete', id)"
    />
  </div>
</template>
