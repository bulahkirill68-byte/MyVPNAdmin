<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const draft = ref(props.modelValue.join(', '))
const parse = (text: string) =>
  text
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
watch(
  () => props.modelValue,
  (values) => {
    if (JSON.stringify(parse(draft.value)) !== JSON.stringify(values)) draft.value = values.join(', ')
  },
)
function input(event: Event) {
  draft.value = (event.target as HTMLInputElement).value
  emit('update:modelValue', parse(draft.value))
}
</script>
<template><input :value="draft" aria-label="Значения через запятую" @input="input" /></template>
