import { useEffect, useRef } from 'react'
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
])

interface Props {
  option: EChartsOption
  height?: number
  label: string
}

export function Chart({ option, height = 320, label }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!el.current) return
    const instance = echarts.init(el.current, null, { renderer: 'canvas' })
    chart.current = instance
    const ro = new ResizeObserver(() => instance.resize())
    ro.observe(el.current)
    return () => {
      ro.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    // notMerge so series that were toggled off actually disappear
    chart.current?.setOption(option, { notMerge: true })
  }, [option])

  return <div ref={el} className="chart" style={{ height }} role="img" aria-label={label} />
}
