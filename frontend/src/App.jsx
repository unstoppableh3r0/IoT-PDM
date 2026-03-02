import { useEffect, useRef, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const TOPIC_DATA = 'iot/pdm/project/data'
const TOPIC_RESULT = 'iot/pdm/project/result'
const MAX_POINTS = 30
const DEMO_VIB_THRESHOLD = 40
const DEMO_STATIC_COUNT = 5

// Placeholder data so the UI always looks good (no MQTT required to render)
const PLACEHOLDER_VIB = [
  { time: '10:00:00', vib: 8.2 },
  { time: '10:00:01', vib: 9.1 },
  { time: '10:00:02', vib: 8.5 },
  { time: '10:00:03', vib: 9.8 },
  { time: '10:00:04', vib: 8.0 },
  { time: '10:00:05', vib: 9.2 },
  { time: '10:00:06', vib: 8.7 },
  { time: '10:00:07', vib: 9.5 },
  { time: '10:00:08', vib: 8.3 },
  { time: '10:00:09', vib: 9.0 },
]
const PLACEHOLDER_RESULT = {
  prediction: 'Healthy',
  explanation: 'Sensors within normal range. No action required.',
  timestamp: new Date().toISOString(),
}
const PLACEHOLDER_LAST_DATA = { vib: 9.0, temp: 42.5 }

function App() {
  const [connected, setConnected] = useState(false)
  const [vibHistory, setVibHistory] = useState(PLACEHOLDER_VIB)
  const [result, setResult] = useState(PLACEHOLDER_RESULT)
  const [lastData, setLastData] = useState(PLACEHOLDER_LAST_DATA)
  const [mqttError, setMqttError] = useState(null)
  const clientRef = useRef(null)

  const isDemoMode = (() => {
    if (vibHistory.length < DEMO_STATIC_COUNT) return false
    const high = vibHistory.some((p) => p.vib >= DEMO_VIB_THRESHOLD)
    const lastVibs = vibHistory.slice(-DEMO_STATIC_COUNT).map((p) => p.vib)
    const allSame = lastVibs.every((v) => v === lastVibs[0])
    return high || allSame
  })()

  useEffect(() => {
    let client = null
    import('mqtt/dist/mqtt.min')
      .then((mod) => {
        const mqtt = mod.default || mod
        // Fallback to mqttdashboard standard websocket broker endpoint
        client = mqtt.connect('ws://broker.mqttdashboard.com:8000/mqtt', {
          reconnectPeriod: 3000,
          connectTimeout: 5000,
        })
        clientRef.current = client

        client.on('connect', () => {
          setConnected(true)
          setMqttError(null)
          client.subscribe(TOPIC_DATA)
          client.subscribe(TOPIC_RESULT)
        })

        client.on('offline', () => setConnected(false))
        client.on('error', (err) => setMqttError(err?.message || 'MQTT error'))

        client.on('message', (topic, payload) => {
          try {
            const msg = JSON.parse(payload.toString())
            if (topic === TOPIC_DATA) {
              setLastData(msg)
              const t = new Date().toLocaleTimeString()
              setVibHistory((prev) => {
                const next = [...prev, { time: t, vib: Number(msg.vib) ?? 0 }]
                return next.slice(-MAX_POINTS)
              })
            } else if (topic === TOPIC_RESULT) {
              setResult(msg)
            }
          } catch (e) {
            console.error('Parse error', e)
          }
        })
      })
      .catch((err) => {
        setMqttError(err?.message || 'MQTT not loaded')
      })

    return () => {
      if (client) client.end()
      clientRef.current = null
    }
  }, [])

  const isFaulty = result?.prediction === 'Faulty'
  const explanation = result?.explanation ?? '—'

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-100">
          Smart IoT Predictive Maintenance
        </h1>
        <div className="flex items-center gap-3">
          {mqttError && (
            <span className="px-3 py-1 rounded-full bg-slate-600 text-slate-200 text-sm">
              Live data off — {mqttError}
            </span>
          )}
          {isDemoMode && (
            <span className="px-3 py-1 rounded-full bg-amber-500/80 text-amber-950 text-sm font-medium">
              DEMO MODE
            </span>
          )}
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${connected ? 'bg-emerald-500/80 text-emerald-950' : 'bg-red-500/80 text-red-950'
              }`}
          >
            {connected ? 'MQTT Connected' : 'Disconnected'}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div
          className={`rounded-2xl p-8 text-center ${isFaulty ? 'bg-red-500/20 border-2 border-red-500' : 'bg-emerald-500/20 border-2 border-emerald-500'
            }`}
        >
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-2">
            Motor Status
          </p>
          <p className={`text-4xl font-bold ${isFaulty ? 'text-red-400' : 'text-emerald-400'}`}>
            {result?.prediction ?? '—'}
          </p>
        </div>

        <div className="lg:col-span-2 rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-2">
            AI Diagnosis (Gemini)
          </p>
          <p className="text-slate-200 text-lg">
            Reason: {explanation}
          </p>
        </div>
      </div>

      <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-200 mb-4">Live Vibration</h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={vibHistory} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="vib"
                name="Vibration"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-slate-200 mb-3">Latest Sensor Data</h2>
        <div className="flex flex-wrap gap-4 text-slate-300">
          <span>Vib: <strong>{lastData?.vib ?? '—'}</strong></span>
          <span>Temp: <strong>{lastData?.temp ?? '—'} °C</strong></span>
        </div>
      </div>
    </div>
  )
}

export default App
