<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
defineProps<{ title: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
onMounted(() => dialog.value?.showModal())
</script>
<template>
  <dialog
    ref="dialog"
    :aria-label="title"
    :class="{ wide }"
    @cancel.prevent="emit('close')"
    @click="
      (e) => {
        if (e.target === dialog) emit('close')
      }
    "
  >
    <div class="modal-head">
      <h2>{{ title }}</h2>
      <button class="icon-btn" aria-label="Закрыть" @click="emit('close')"><X :size="20" /></button>
    </div>
    <slot />
  </dialog>
</template>
