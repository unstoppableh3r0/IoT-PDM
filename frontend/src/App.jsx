import { useEffect, useRef, useState, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts'

const TOPIC_DATA = 'iot/pdm/project/data'
const TOPIC_RESULT = 'iot/pdm/project/result'
const TOPIC_EXPLAIN_REQ = 'iot/pdm/project/explain'
const TOPIC_EXPLAIN_RES = 'iot/pdm/project/explanation'
const MAX_POINTS = 30
const MAX_HISTORY = 50
const DEMO_VIB_THRESHOLD = 40
const DEMO_STATIC_COUNT = 5

// Warning thresholds for visual reference lines
const VIB_WARN = 25
const VIB_DANGER = 35
const TEMP_WARN = 40
const TEMP_DANGER = 50

// Placeholder data
const PLACEHOLDER_SENSOR = [
  { time: '10:00:00', vib: 8.2, temp: 28.1 },
  { time: '10:00:01', vib: 9.1, temp: 28.3 },
  { time: '10:00:02', vib: 8.5, temp: 28.0 },
  { time: '10:00:03', vib: 9.8, temp: 28.5 },
  { time: '10:00:04', vib: 8.0, temp: 27.9 },
  { time: '10:00:05', vib: 9.2, temp: 28.2 },
  { time: '10:00:06', vib: 8.7, temp: 28.4 },
  { time: '10:00:07', vib: 9.5, temp: 28.1 },
  { time: '10:00:08', vib: 8.3, temp: 28.6 },
  { time: '10:00:09', vib: 9.0, temp: 28.3 },
]
const PLACEHOLDER_RESULT = {
  prediction: 'Healthy',
  timestamp: new Date().toISOString(),
}
const PLACEHOLDER_LAST_DATA = { vib: 9.0, temp: 28.3 }

function App() {
  const [connected, setConnected] = useState(false)
  const [sensorHistory, setSensorHistory] = useState(PLACEHOLDER_SENSOR)
  const [result, setResult] = useState(PLACEHOLDER_RESULT)
  const [lastData, setLastData] = useState(PLACEHOLDER_LAST_DATA)
  const [mqttError, setMqttError] = useState(null)
  const [explanation, setExplanation] = useState(null)
  const [explainLoading, setExplainLoading] = useState(false)
  const [lastDataTime, setLastDataTime] = useState(null)
  const [lastResultTime, setLastResultTime] = useState(null)
  const [logs, setLogs] = useState([])
  const [predictionHistory, setPredictionHistory] = useState([])
  const [stats, setStats] = useState({ total: 0, healthy: 0, faulty: 0, startTime: Date.now() })
  const clientRef = useRef(null)

  const addLog = useCallback((msg) => {
    const ts = new Date().toLocaleTimeString()
    console.log(`[MQTT ${ts}] ${msg}`)
    setLogs((prev) => [`[${ts}] ${msg}`, ...prev].slice(0, 50))
  }, [])

  const isDemoMode = (() => {
    if (sensorHistory.length < DEMO_STATIC_COUNT) return false
    const high = sensorHistory.some((p) => p.vib >= DEMO_VIB_THRESHOLD)
    const lastVibs = sensorHistory.slice(-DEMO_STATIC_COUNT).map((p) => p.vib)
    const allSame = lastVibs.every((v) => v === lastVibs[0])
    return high || allSame
  })()

  useEffect(() => {
    let client = null
    addLog('Loading MQTT library...')
    import('mqtt')
      .then((mod) => {
        const mqtt = mod.default || mod
        const connectFn = mqtt.connect || mod.connect
        addLog('Connecting to broker.mqttdashboard.com:8000...')
        client = connectFn('ws://broker.mqttdashboard.com:8000/mqtt', {
          reconnectPeriod: 3000,
          connectTimeout: 5000,
        })
        clientRef.current = client

        client.on('connect', () => {
          setConnected(true)
          setMqttError(null)
          addLog('Connected! Subscribing to topics...')
          client.subscribe(TOPIC_DATA, (err) => {
            addLog(err ? `Sub ${TOPIC_DATA} FAILED: ${err.message}` : `Subscribed: ${TOPIC_DATA}`)
          })
          client.subscribe(TOPIC_RESULT, (err) => {
            addLog(err ? `Sub ${TOPIC_RESULT} FAILED: ${err.message}` : `Subscribed: ${TOPIC_RESULT}`)
          })
          client.subscribe(TOPIC_EXPLAIN_RES, (err) => {
            addLog(err ? `Sub ${TOPIC_EXPLAIN_RES} FAILED: ${err.message}` : `Subscribed: ${TOPIC_EXPLAIN_RES}`)
          })
        })

        client.on('reconnect', () => addLog('Reconnecting...'))
        client.on('offline', () => { setConnected(false); addLog('Went offline') })
        client.on('error', (err) => {
          const msg = err?.message || 'MQTT error'
          setMqttError(msg)
          addLog(`Error: ${msg}`)
        })

        client.on('message', (topic, payload) => {
          try {
            const raw = payload.toString()
            const msg = JSON.parse(raw)
            addLog(`<< [${topic}] ${raw.slice(0, 120)}`)

            if (topic === TOPIC_DATA) {
              setLastData(msg)
              setLastDataTime(new Date())
              const t = new Date().toLocaleTimeString()
              setSensorHistory((prev) => {
                const next = [...prev, {
                  time: t,
                  vib: Number(msg.vib) ?? 0,
                  temp: Number(msg.temp) ?? 0,
                }]
                return next.slice(-MAX_POINTS)
              })
            } else if (topic === TOPIC_RESULT) {
              setLastResultTime(new Date())
              if (msg.vib != null || msg.temp != null) {
                setLastData((prev) => ({
                  ...prev,
                  ...(msg.vib != null && { vib: msg.vib }),
                  ...(msg.temp != null && { temp: msg.temp }),
                }))
              }
              // Track prediction history
              setPredictionHistory((prev) => [{
                time: new Date().toLocaleTimeString(),
                prediction: msg.prediction,
                vib: msg.vib,
                temp: msg.temp,
              }, ...prev].slice(0, MAX_HISTORY))
              // Update stats
              setStats((prev) => ({
                ...prev,
                total: prev.total + 1,
                healthy: prev.healthy + (msg.prediction === 'Healthy' ? 1 : 0),
                faulty: prev.faulty + (msg.prediction === 'Faulty' ? 1 : 0),
              }))
              // Only clear explanation if prediction changed
              setResult((prev) => {
                if (prev?.prediction !== msg.prediction) {
                  setExplanation(null)
                }
                return msg
              })
            } else if (topic === TOPIC_EXPLAIN_RES) {
              setExplanation(msg.explanation || 'No explanation available.')
              setExplainLoading(false)
            }
          } catch (e) {
            addLog(`Parse error on [${topic}]: ${e.message}`)
            console.error('Parse error', e)
          }
        })
      })
      .catch((err) => {
        const msg = err?.message || 'MQTT not loaded'
        setMqttError(msg)
        addLog(`Load error: ${msg}`)
      })

    return () => {
      if (client) client.end()
      clientRef.current = null
    }
  }, [addLog])

  const isFaulty = result?.prediction === 'Faulty'

  const handleAskAI = () => {
    if (!clientRef.current || !connected) return
    setExplainLoading(true)
    setExplanation(null)
    const payload = JSON.stringify({ request: 'explain' })
    clientRef.current.publish(TOPIC_EXPLAIN_REQ, payload)
    addLog(`>> [${TOPIC_EXPLAIN_REQ}] ${payload}`)
  }

  const formatAgo = (date) => {
    if (!date) return 'never'
    const secs = Math.floor((Date.now() - date.getTime()) / 1000)
    if (secs < 5) return 'just now'
    if (secs < 60) return `${secs}s ago`
    return `${Math.floor(secs / 60)}m ago`
  }

  const formatUptime = () => {
    const secs = Math.floor((Date.now() - stats.startTime) / 1000)
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = secs % 60
    if (h > 0) return `${h}h ${m}m ${s}s`
    if (m > 0) return `${m}m ${s}s`
    return `${s}s`
  }

  const faultRate = stats.total > 0 ? ((stats.faulty / stats.total) * 100).toFixed(1) : '0.0'

  // Re-render every second to update "ago" times and uptime
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const chartTooltipStyle = {
    backgroundColor: '#1e293b',
    border: '1px solid #475569',
    borderRadius: '8px',
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-4 md:p-6">
      {/* Header */}
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            Smart IoT Predictive Maintenance
          </h1>
          <p className="text-sm text-slate-500 mt-1">Real-time motor health monitoring & AI diagnosis</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {mqttError && (
            <span className="px-3 py-1 rounded-full bg-slate-600 text-slate-200 text-sm">
              {mqttError}
            </span>
          )}
          {isDemoMode && (
            <span className="px-3 py-1 rounded-full bg-amber-500/80 text-amber-950 text-sm font-medium animate-pulse">
              DEMO MODE
            </span>
          )}
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${connected ? 'bg-emerald-500/80 text-emerald-950' : 'bg-red-500/80 text-red-950'}`}
          >
            {connected ? 'MQTT Connected' : 'Disconnected'}
          </span>
        </div>
      </header>

      {/* Top Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {/* Motor Status - large */}
        <div
          className={`col-span-2 lg:col-span-1 rounded-2xl p-6 text-center transition-colors duration-500 ${
            isFaulty
              ? 'bg-red-500/20 border-2 border-red-500'
              : 'bg-emerald-500/20 border-2 border-emerald-500'
          }`}
        >
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Motor Status</p>
          <p className={`text-3xl font-bold ${isFaulty ? 'text-red-400' : 'text-emerald-400'}`}>
            {result?.prediction ?? '—'}
          </p>
          {lastResultTime && (
            <p className="text-xs text-slate-500 mt-1">{formatAgo(lastResultTime)}</p>
          )}
        </div>

        {/* Vibration */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Vibration</p>
          <p className={`text-2xl font-bold ${
            (lastData?.vib ?? 0) >= VIB_DANGER ? 'text-red-400' :
            (lastData?.vib ?? 0) >= VIB_WARN ? 'text-amber-400' : 'text-sky-400'
          }`}>
            {lastData?.vib ?? '—'}
          </p>
          <p className="text-xs text-slate-500">unit</p>
        </div>

        {/* Temperature */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Temperature</p>
          <p className={`text-2xl font-bold ${
            (lastData?.temp ?? 0) >= TEMP_DANGER ? 'text-red-400' :
            (lastData?.temp ?? 0) >= TEMP_WARN ? 'text-amber-400' : 'text-orange-400'
          }`}>
            {lastData?.temp ?? '—'} <span className="text-base font-normal">°C</span>
          </p>
          <p className="text-xs text-slate-500">ambient</p>
        </div>

        {/* Fault Rate */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Fault Rate</p>
          <p className={`text-2xl font-bold ${
            Number(faultRate) > 20 ? 'text-red-400' :
            Number(faultRate) > 5 ? 'text-amber-400' : 'text-emerald-400'
          }`}>
            {faultRate}<span className="text-base font-normal">%</span>
          </p>
          <p className="text-xs text-slate-500">{stats.faulty}/{stats.total} readings</p>
        </div>

        {/* Uptime */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Session Uptime</p>
          <p className="text-2xl font-bold text-violet-400">{formatUptime()}</p>
          <p className="text-xs text-slate-500">monitoring</p>
        </div>
      </div>

      {/* AI Diagnosis */}
      <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6 mb-6">
        <p className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">
          AI Diagnosis (Gemini)
        </p>
        {explanation ? (
          <div className="flex items-start gap-3">
            <span className="text-2xl">🤖</span>
            <div>
              <p className="text-slate-200 text-lg">{explanation}</p>
              <button
                onClick={() => setExplanation(null)}
                className="text-xs text-slate-500 hover:text-slate-300 mt-2 underline"
              >
                Clear
              </button>
            </div>
          </div>
        ) : isFaulty ? (
          <div className="flex items-center gap-4">
            <span className="text-amber-400 text-sm">Fault detected —</span>
            <button
              onClick={handleAskAI}
              disabled={explainLoading || !connected}
              className="px-5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-900 font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {explainLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  Asking AI...
                </span>
              ) : 'Ask AI for Diagnosis'}
            </button>
          </div>
        ) : (
          <p className="text-slate-500">Motor is healthy — no diagnosis needed.</p>
        )}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Vibration Chart */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-4">Live Vibration</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} />
                <Tooltip contentStyle={chartTooltipStyle} labelStyle={{ color: '#e2e8f0' }} />
                <Legend />
                <ReferenceLine y={VIB_WARN} stroke="#f59e0b" strokeDasharray="5 5" label={{ value: 'Warning', fill: '#f59e0b', fontSize: 10 }} />
                <ReferenceLine y={VIB_DANGER} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Danger', fill: '#ef4444', fontSize: 10 }} />
                <Line type="monotone" dataKey="vib" name="Vibration" stroke="#38bdf8" strokeWidth={2} dot={false} animationDuration={300} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Temperature Chart */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-4">Live Temperature</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} unit="°C" />
                <Tooltip contentStyle={chartTooltipStyle} labelStyle={{ color: '#e2e8f0' }} formatter={(v) => [`${v} °C`, 'Temperature']} />
                <Legend />
                <ReferenceLine y={TEMP_WARN} stroke="#f59e0b" strokeDasharray="5 5" label={{ value: 'Warning', fill: '#f59e0b', fontSize: 10 }} />
                <ReferenceLine y={TEMP_DANGER} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Danger', fill: '#ef4444', fontSize: 10 }} />
                <Line type="monotone" dataKey="temp" name="Temperature" stroke="#fb923c" strokeWidth={2} dot={false} animationDuration={300} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Prediction History */}
      <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-200 mb-3">Prediction History</h2>
        {predictionHistory.length === 0 ? (
          <p className="text-slate-500 text-sm">No predictions yet — waiting for backend results...</p>
        ) : (
          <div className="max-h-48 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-xs uppercase sticky top-0 bg-slate-800">
                <tr>
                  <th className="text-left py-2 px-3">Time</th>
                  <th className="text-left py-2 px-3">Status</th>
                  <th className="text-right py-2 px-3">Vibration</th>
                  <th className="text-right py-2 px-3">Temp (°C)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {predictionHistory.map((entry, i) => (
                  <tr key={i} className="hover:bg-slate-700/30">
                    <td className="py-1.5 px-3 text-slate-400 font-mono text-xs">{entry.time}</td>
                    <td className="py-1.5 px-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${
                        entry.prediction === 'Faulty'
                          ? 'bg-red-500/20 text-red-400'
                          : 'bg-emerald-500/20 text-emerald-400'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          entry.prediction === 'Faulty' ? 'bg-red-400' : 'bg-emerald-400'
                        }`}/>
                        {entry.prediction}
                      </span>
                    </td>
                    <td className="py-1.5 px-3 text-right text-slate-300">{entry.vib ?? '—'}</td>
                    <td className="py-1.5 px-3 text-right text-slate-300">{entry.temp ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* MQTT Log Panel */}
      <details className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
        <summary className="text-lg font-semibold text-slate-200 cursor-pointer select-none">
          MQTT Logs ({logs.length})
        </summary>
        <div className="mt-3 max-h-48 overflow-y-auto font-mono text-xs text-slate-400 space-y-1">
          {logs.length === 0 ? (
            <p className="text-slate-500">No logs yet — waiting for MQTT activity...</p>
          ) : (
            logs.map((log, i) => <p key={i}>{log}</p>)
          )}
        </div>
      </details>
    </div>
  )
}

export default App
