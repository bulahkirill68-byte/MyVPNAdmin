<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { use, init, type ECharts } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { bytes, type Traffic } from '../api'
use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
const props = defineProps<{ data: Traffic[] }>()
const el = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver
function render() {
  chart?.setOption({
    animation: !matchMedia('(prefers-reduced-motion: reduce)').matches,
    animationDuration: 300,
    grid: { left: 58, right: 15, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => bytes(v) },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#536078' } },
      splitLine: { show: false },
      axisLabel: { color: '#92a0b7' },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#92a0b7', formatter: (v: number) => bytes(v) },
      splitLine: { lineStyle: { color: '#53607825' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: props.data.length < 3,
        symbolSize: 7,
        itemStyle: { color: '#3dc9bd' },
        lineStyle: { width: 3 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#3dc9bd40' },
              { offset: 1, color: '#3dc9bd00' },
            ],
          },
        },
        data: props.data.map((p) => [p.at * 1000, p.bytes]),
      },
    ],
  })
}
onMounted(() => {
  if (el.value) {
    chart = init(el.value)
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(el.value)
    render()
  }
})
watch(() => props.data, render)
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>
<template>
  <div v-if="!data.length" class="empty chart-empty">
    <span class="empty-orbit">↗</span><strong>Здесь появится ваш трафик</strong>
    <p>Нет измерений за последние 7 дней. Данные поступают из StatsService Xray.</p>
  </div>
  <div
    v-show="data.length"
    ref="el"
    class="chart"
    role="img"
    aria-label="Фактический трафик по часам за последние 7 дней"
  />
</template>
