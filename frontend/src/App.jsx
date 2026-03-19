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
import { BROKER_CONFIG, TOPICS } from './mqttConfig'

const TOPIC_DATA = TOPICS.DATA
const TOPIC_RESULT = TOPICS.RESULT
const TOPIC_EXPLAIN_REQ = TOPICS.EXPLAIN_REQ
const TOPIC_EXPLAIN_RES = TOPICS.EXPLAIN_RES
const TOPIC_RETRAIN_REQ = TOPICS.RETRAIN_REQ
const TOPIC_RETRAIN_RES = TOPICS.RETRAIN_RES
const TOPIC_FEEDBACK = TOPICS.FEEDBACK
const TOPIC_CONTROL = TOPICS.CONTROL
const MAX_POINTS = 30
const MAX_HISTORY = 50
const DEMO_VIB_THRESHOLD = 40
const DEMO_STATIC_COUNT = 5
const FAULT_WINDOW_SIZE = 10  // Track last 10 readings
const FAULT_THRESHOLD_COUNT = 5  // Mark faulty if 5+ out of 10 are faulted

// VMC Physics-Based Warning Thresholds (ISO 10816 & Industrial Standards)
const VIB_WARN = 12  // ISO 10816 elevated vibration (pitting start)
const VIB_DANGER = 15  // ISO 10816 critical pitting threshold
const TEMP_WARN = 50  // Industrial bearing warning temperature
const TEMP_DANGER = 60  // Industrial thermal runout threshold

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
  const [retrainLoading, setRetrainLoading] = useState(false)
  const [retrainResult, setRetrainResult] = useState(null)
  const [thresholdFault, setThresholdFault] = useState(null)  // Tracks threshold breach faults
  const [faultExplanation, setFaultExplanation] = useState(null)  // Separate explanation for threshold fault
  const [faultExplainLoading, setFaultExplainLoading] = useState(false)
  const [recentReadings, setRecentReadings] = useState([])  // Sliding window of recent readings for fault stability
  // Predictive Maintenance Tracking
  const [baselineData, setBaselineData] = useState(null)  // Healthy baseline readings
  const [healthScore, setHealthScore] = useState(100)  // 0-100 health score
  const [vibrationTrend, setVibrationTrend] = useState(0)  // -1: declining, 0: stable, 1: rising
  const [temperatureTrend, setTemperatureTrend] = useState(0)  // -1: declining, 0: stable, 1: rising
  const [estimatedRUL, setEstimatedRUL] = useState(null)  // Remaining Useful Life in hours
  const [anomalyAlerts, setAnomalyAlerts] = useState([])  // Recent anomalies detected
  const [maintenanceRecommendation, setMaintenanceRecommendation] = useState(null)  // Maintenance scheduling
  // Hybrid LoRa/MQTT Communication Tracking
  const [commStats, setCommStats] = useState(null)  // Communication statistics
  const [loraActive, setLoraActive] = useState(false)  // Whether LoRa is actively receiving
  const [hasSeenFault, setHasSeenFault] = useState(false)  // Track if any fault was seen in session
  const explainRequestTypeRef = useRef(null)  // Track which explanation was requested: 'prediction' or 'threshold'
  const clientRef = useRef(null)

  const addLog = useCallback((msg) => {
    const ts = new Date().toLocaleTimeString()
    console.log(`[MQTT ${ts}] ${msg}`)
    setLogs((prev) => [`[${ts}] ${msg}`, ...prev].slice(0, 50))
  }, [])

  // Calculate predictive maintenance metrics
  const calculatePredictiveMetrics = useCallback((newReading) => {
    // 1. Set baseline if not already set (first few healthy readings)
    if (!baselineData) {
      setBaselineData({
        vib: 10,  // Typical healthy baseline
        temp: 30,
        timestamp: Date.now()
      })
    }

    const base = baselineData || { vib: 10, temp: 30 }
    const currentVib = newReading.vib ?? 0
    const currentTemp = newReading.temp ?? 0

    // 2. Calculate Health Score (0-100) based on current state
    const vibDistance = Math.min(Math.max(0, currentVib - base.vib) / 15, 1) // 0-15 point scale
    const tempDistance = Math.min(Math.max(0, currentTemp - base.temp) / 30, 1) // 0-30 point scale
    const newHealthScore = Math.max(0, 100 - (vibDistance * 50 + tempDistance * 50))
    setHealthScore(Math.round(newHealthScore))

    // Use recent readings for calculations
    setRecentReadings((prev) => {
      if (prev.length < 2) return prev

      // 3. Calculate trends from recent window
      const last5 = prev.slice(-5)
      const prev5 = prev.slice(Math.max(0, prev.length - 10), Math.max(0, prev.length - 5))

      if (last5.length > 0 && prev5.length > 0) {
        const recentVibAvg = last5.reduce((a, b) => a + b.vib, 0) / last5.length
        const prevVibAvg = prev5.reduce((a, b) => a + b.vib, 0) / prev5.length
        const vibTrend = recentVibAvg > prevVibAvg + 1 ? 1 : recentVibAvg < prevVibAvg - 1 ? -1 : 0
        setVibrationTrend(vibTrend)

        const recentTempAvg = last5.reduce((a, b) => a + b.temp, 0) / last5.length
        const prevTempAvg = prev5.reduce((a, b) => a + b.temp, 0) / prev5.length
        const tempTrend = recentTempAvg > prevTempAvg + 1 ? 1 : recentTempAvg < prevTempAvg - 1 ? -1 : 0
        setTemperatureTrend(tempTrend)

        // 4. Estimate RUL (Remaining Useful Life) in hours
        const distanceToDanger = Math.min(
          Math.max(0, VIB_DANGER - currentVib) / 3,
          Math.max(0, TEMP_DANGER - currentTemp) / 5
        )
        const degradationRate = vibTrend === 1 ? 1.5 : tempTrend === 1 ? 1.2 : 0.8
        const estimatedHours = Math.max(0.5, Math.round((distanceToDanger / degradationRate) * 24))
        setEstimatedRUL(estimatedHours)
      }

      // 5. Detect anomalies (readings that deviate from pattern)
      if (prev.length > 3) {
        const avgVib = prev.slice(-5).reduce((a, b) => a + b.vib, 0) / Math.min(5, prev.length)
        const avgTemp = prev.slice(-5).reduce((a, b) => a + b.temp, 0) / Math.min(5, prev.length)
        const vibDeviation = Math.abs(currentVib - avgVib)
        const tempDeviation = Math.abs(currentTemp - avgTemp)

        if (vibDeviation > 3 || tempDeviation > 5) {
          const anomaly = {
            type: vibDeviation > 3 ? 'Vibration Spike' : 'Temperature Spike',
            value: vibDeviation > 3 ? `+${vibDeviation.toFixed(1)} m/s²` : `+${tempDeviation.toFixed(1)}°C`,
            timestamp: new Date().toLocaleTimeString()
          }
          setAnomalyAlerts((prev) => [anomaly, ...prev].slice(0, 5))
        }
      }

      // 6. Generate maintenance recommendation based on health score
      const faultRatio = prev.filter(r => r.isFaulted).length / prev.length
      if (faultRatio > 0.1) setHasSeenFault(true) // Persistent trigger

      let recommendation = null
      if (newHealthScore < 30 || faultRatio > 0.5) {
        recommendation = { severity: 'CRITICAL', message: 'Immediate maintenance required — motor failure imminent', color: 'red' }
      } else if (newHealthScore < 50 || faultRatio > 0.3) {
        recommendation = { severity: 'HIGH', message: 'Schedule maintenance within 24 hours', color: 'amber' }
      } else if (newHealthScore < 70 || faultRatio > 0.1) {
        recommendation = { severity: 'MEDIUM', message: 'Plan maintenance for next scheduled downtime', color: 'yellow' }
      } else {
        recommendation = { severity: 'LOW', message: 'Motor running healthy — continue monitoring', color: 'green' }
      }
      setMaintenanceRecommendation(recommendation)

      return prev
    })
  }, [baselineData])

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
        addLog(`Connecting to ${BROKER_CONFIG.host}:${BROKER_CONFIG.port}...`)
        client = connectFn(BROKER_CONFIG.url, {
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
          client.subscribe(TOPIC_RETRAIN_RES, (err) => {
            addLog(err ? `Sub ${TOPIC_RETRAIN_RES} FAILED: ${err.message}` : `Subscribed: ${TOPIC_RETRAIN_RES}`)
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

              const vibVal = Number(msg.vib)
              const tempVal = Number(msg.temp)

              setSensorHistory((prev) => {
                const entry = { time: t }
                // Only add valid numbers, skip error codes like -1
                if (!isNaN(vibVal) && vibVal >= 0) entry.vib = vibVal
                if (!isNaN(tempVal) && tempVal > 0) entry.temp = tempVal

                if (entry.vib !== undefined || entry.temp !== undefined) {
                  return [...prev, entry].slice(-MAX_POINTS)
                }
                return prev
              })
            } else if (topic === TOPIC_RESULT) {
              setLastResultTime(new Date())

              // Extract values for graph plotting
              const vibValue = msg.vib !== undefined ? Number(msg.vib) : null
              const tempValue = msg.temp !== undefined ? Number(msg.temp) : null

              if (vibValue !== null || tempValue !== null) {
                // Update Last Data display
                setLastData((prev) => ({
                  ...prev,
                  ...(vibValue !== null && !isNaN(vibValue) && { vib: vibValue }),
                  ...(tempValue !== null && !isNaN(tempValue) && { temp: tempValue }),
                }))

                // Update live graph history
                const t = msg.timestamp
                  ? new Date(msg.timestamp).toLocaleTimeString()
                  : new Date().toLocaleTimeString()

                setSensorHistory((prev) => {
                  const entry = { time: t }
                  // Filter out NaN and error values (-1)
                  if (vibValue !== null && !isNaN(vibValue) && vibValue >= 0) entry.vib = vibValue
                  if (tempValue !== null && !isNaN(tempValue) && tempValue > 0) entry.temp = tempValue

                  if (entry.vib !== undefined || entry.temp !== undefined) {
                    return [...prev, entry].slice(-MAX_POINTS)
                  }
                  return prev
                })

                // Fault Detection
                const vib = !isNaN(vibValue) ? vibValue : 0
                const temp = !isNaN(tempValue) ? tempValue : 0
                const isFaultedReading = vib > VIB_DANGER || temp > TEMP_DANGER

                setRecentReadings((prev) => {
                  const updated = [...prev, {
                    timestamp: msg.timestamp || new Date().toISOString(),
                    vib: vib,
                    temp: temp,
                    isFaulted: isFaultedReading
                  }].slice(-FAULT_WINDOW_SIZE)

                  const faultCount = updated.filter(r => r.isFaulted).length

                  if (faultCount >= FAULT_THRESHOLD_COUNT) {
                    setThresholdFault({
                      timestamp: msg.timestamp || new Date().toISOString(),
                      vib: vib,
                      temp: temp,
                      reason: vib > VIB_DANGER ? `Vibration ${vib} exceeds danger threshold (${VIB_DANGER})` : `Temperature ${temp}°C exceeds danger threshold (${TEMP_DANGER}°C)`,
                      faultCount: faultCount,
                      windowSize: updated.length
                    })
                    setFaultExplanation(null)
                  } else if (faultCount < FAULT_THRESHOLD_COUNT - 2) {
                    setThresholdFault(null)
                  }
                  return updated
                })

                // Metrics
                if (msg.health_score != null) setHealthScore(msg.health_score)
                if (msg.baseline != null) setBaselineData(msg.baseline)
                if (msg.trend != null) {
                  const trend = msg.trend
                  setVibrationTrend(trend.vib_trend === 'rising' ? 1 : trend.vib_trend === 'falling' ? -1 : 0)
                  setTemperatureTrend(trend.temp_trend === 'rising' ? 1 : trend.temp_trend === 'falling' ? -1 : 0)
                }
                if (msg.rul_days != null) setEstimatedRUL(msg.rul_days)

                if (msg.anomalies != null && (msg.anomalies.vib_anomaly || msg.anomalies.temp_anomaly)) {
                  const alerts = []
                  if (msg.anomalies.vib_anomaly) {
                    alerts.push({
                      type: 'Vibration Anomaly',
                      value: `Z-score: ${msg.anomalies.vib_z_score}`,
                      timestamp: new Date().toLocaleTimeString()
                    })
                  }
                  if (msg.anomalies.temp_anomaly) {
                    alerts.push({
                      type: 'Temperature Anomaly',
                      value: `Z-score: ${msg.anomalies.temp_z_score}`,
                      timestamp: new Date().toLocaleTimeString()
                    })
                  }
                  if (alerts.length > 0) {
                    setAnomalyAlerts((prev) => [...alerts, ...prev].slice(0, 10))
                  }
                }

                // Comm Stats
                if (msg.comm_stats) {
                  setCommStats(msg.comm_stats)
                  setLoraActive(msg.comm_stats.last_source === 'lora' || msg.comm_stats.lora_messages > 0)
                }

                calculatePredictiveMetrics({ vib, temp })
              }

              // Prediction History
              setPredictionHistory((prev) => [{
                time: new Date().toLocaleTimeString(),
                timestamp: msg.timestamp,
                prediction: msg.prediction || 'Unknown',
                vib: msg.vib,
                temp: msg.temp,
                health_score: msg.health_score,
                rul_days: msg.rul_days,
                feedbackSent: false,
                correctedLabel: null,
              }, ...prev].slice(0, MAX_HISTORY))

              setStats((prev) => ({
                ...prev,
                total: prev.total + 1,
                healthy: prev.healthy + (msg.prediction === 'Healthy' ? 1 : 0),
                faulty: prev.faulty + (msg.prediction === 'Faulty' ? 1 : 0),
              }))

              setResult((prev) => {
                if (prev?.prediction !== msg.prediction) setExplanation(null)
                if (msg.prediction === 'Faulty') setHasSeenFault(true)
                return msg
              })
            } else if (topic === TOPIC_EXPLAIN_RES) {
              if (explainRequestTypeRef.current === 'threshold') {
                setFaultExplanation(msg.explanation || 'No explanation available.')
                setFaultExplainLoading(false)
              } else {
                setExplanation(msg.explanation || 'No explanation available.')
                setExplainLoading(false)
              }
            } else if (topic === TOPIC_RETRAIN_RES) {
              setRetrainResult(msg)
              setRetrainLoading(false)
              addLog(`Retrain result: ${msg.message || msg.status}`)
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

  const handleAskAI = () => {
    if (!clientRef.current || !connected) return
    setExplainLoading(true)
    setExplanation(null)
    explainRequestTypeRef.current = 'prediction'
    const payload = JSON.stringify({ request: 'explain' })
    clientRef.current.publish(TOPIC_EXPLAIN_REQ, payload)
    addLog(`>> [${TOPIC_EXPLAIN_REQ}] ${payload}`)
  }

  const handleAskAIForThresholdFault = () => {
    if (!clientRef.current || !connected) return
    setFaultExplainLoading(true)
    setFaultExplanation(null)
    explainRequestTypeRef.current = 'threshold'
    const payload = JSON.stringify({ request: 'explain' })
    clientRef.current.publish(TOPIC_EXPLAIN_REQ, payload)
    addLog(`>> [${TOPIC_EXPLAIN_REQ}] (threshold fault) ${payload}`)
  }

  const handleRetrain = () => {
    if (!clientRef.current || !connected) return
    setRetrainLoading(true)
    setRetrainResult(null)
    const payload = JSON.stringify({ request: 'retrain' })
    clientRef.current.publish(TOPIC_RETRAIN_REQ, payload)
    addLog(`>> [${TOPIC_RETRAIN_REQ}] ${payload}`)
  }

  const handleFeedback = (entry, correctedLabel) => {
    if (!clientRef.current || !connected) return
    const payload = JSON.stringify({
      timestamp: entry.timestamp,
      label: correctedLabel, // 0 = Healthy, 1 = Faulty
    })
    clientRef.current.publish(TOPIC_FEEDBACK, payload)
    addLog(`>> [${TOPIC_FEEDBACK}] ${payload}`)
    // Update local history to show feedback was sent
    setPredictionHistory((prev) =>
      prev.map((p) =>
        p.timestamp === entry.timestamp
          ? { ...p, feedbackSent: true, correctedLabel }
          : p
      )
    )
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

  // Motor is faulty if prediction says so OR if recent readings show fault pattern (N faults in last 10)
  const recentFaultCount = recentReadings.filter(r => r.isFaulted).length
  const isFaulty = result?.prediction === 'Faulty' || recentFaultCount >= FAULT_THRESHOLD_COUNT

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
          {loraActive && (
            <span className="px-3 py-1 rounded-full text-sm font-medium bg-blue-500/80 text-blue-950 flex items-center gap-1">
              📡 LoRa Active
              {commStats && commStats.current_rssi && (
                <span className="text-xs opacity-75">
                  ({commStats.current_rssi} dBm)
                </span>
              )}
            </span>
          )}
        </div>
      </header>

      {/* Top Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {/* Motor Status - large */}
        <div
          className={`col-span-2 lg:col-span-1 rounded-2xl p-6 text-center transition-colors duration-500 ${isFaulty
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
          <p className={`text-2xl font-bold ${(lastData?.vib ?? 0) >= VIB_DANGER ? 'text-red-400' :
            (lastData?.vib ?? 0) >= VIB_WARN ? 'text-amber-400' : 'text-sky-400'
            }`}>
            {lastData?.vib ?? '—'}
          </p>
          <p className="text-xs text-slate-500">unit</p>
        </div>

        {/* Temperature */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Temperature</p>
          <p className={`text-2xl font-bold ${(lastData?.temp ?? 0) >= TEMP_DANGER ? 'text-red-400' :
            (lastData?.temp ?? 0) >= TEMP_WARN ? 'text-amber-400' : 'text-orange-400'
            }`}>
            {lastData?.temp ?? '—'} <span className="text-base font-normal">°C</span>
          </p>
          <p className="text-xs text-slate-500">ambient</p>
        </div>

        {/* Fault Rate */}
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-4 text-center">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Fault Rate</p>
          <p className={`text-2xl font-bold ${Number(faultRate) > 20 ? 'text-red-400' :
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

      {/* Demo controls removed as per user request — now terminal only */}

      {/* Hybrid Communication Statistics */}
      {commStats && (
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6 mb-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <span>📡</span> Hybrid Communication Status
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total Messages</p>
              <p className="text-2xl font-bold text-slate-200">{commStats.total_messages}</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">LoRa Messages</p>
              <p className="text-2xl font-bold text-blue-400">{commStats.lora_messages}</p>
              <p className="text-xs text-slate-500">{commStats.lora_percentage}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">WiFi/MQTT</p>
              <p className="text-2xl font-bold text-green-400">{commStats.mqtt_messages}</p>
              <p className="text-xs text-slate-500">{(100 - commStats.lora_percentage).toFixed(1)}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Active Nodes</p>
              <p className="text-2xl font-bold text-purple-400">{commStats.active_lora_nodes}</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Signal (RSSI)</p>
              <p className={`text-2xl font-bold ${commStats.lora_rssi_avg > -80 ? 'text-green-400' :
                commStats.lora_rssi_avg > -100 ? 'text-amber-400' : 'text-red-400'
                }`}>
                {commStats.lora_rssi_avg ? `${commStats.lora_rssi_avg} dBm` : '—'}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Quality (SNR)</p>
              <p className={`text-2xl font-bold ${commStats.lora_snr_avg > 5 ? 'text-green-400' :
                commStats.lora_snr_avg > 0 ? 'text-amber-400' : 'text-red-400'
                }`}>
                {commStats.lora_snr_avg ? `${commStats.lora_snr_avg} dB` : '—'}
              </p>
            </div>
          </div>
          {commStats.node_id && (
            <div className="mt-4 pt-4 border-t border-slate-700 text-sm text-slate-400">
              <span className="font-medium">Current Source:</span> {commStats.last_source === 'lora' ? '📡 LoRa' : '📶 WiFi/MQTT'}
              {commStats.node_id && <span className="ml-3">| <span className="font-medium">Node:</span> {commStats.node_id}</span>}
              {commStats.gateway && <span className="ml-3">| <span className="font-medium">Gateway:</span> {commStats.gateway}</span>}
            </div>
          )}
        </div>
      )}

      {/* Main Grid: Health Score & RUL + Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className={`lg:col-span-1 rounded-2xl p-6 border-2 ${healthScore >= 70 ? 'bg-emerald-500/10 border-emerald-500' :
          healthScore >= 50 ? 'bg-amber-500/10 border-amber-500' :
            'bg-red-500/10 border-red-500'
          }`}>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">Health Score</p>
          <div className="text-center">
            <p className={`text-5xl font-bold ${healthScore >= 70 ? 'text-emerald-400' :
              healthScore >= 50 ? 'text-amber-400' :
                'text-red-400'
              }`}>{healthScore}</p>
            <p className="text-slate-400 text-sm mt-2">/100</p>
            <div className="w-full bg-slate-700 rounded-full h-2 mt-4">
              <div
                className={`h-2 rounded-full transition-all ${healthScore >= 70 ? 'bg-emerald-500' :
                  healthScore >= 50 ? 'bg-amber-500' :
                    'bg-red-500'
                  }`}
                style={{ width: `${healthScore}%` }}
              />
            </div>
          </div>
        </div>

        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-4">Trends</p>
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Vibration</span>
                <span className={`font-bold ${vibrationTrend > 0 ? 'text-red-400' :
                  vibrationTrend < 0 ? 'text-emerald-400' :
                    'text-slate-300'
                  }`}>
                  {vibrationTrend > 0 ? '📈 Rising' : vibrationTrend < 0 ? '📉 Declining' : '➡️ Stable'}
                </span>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Temperature</span>
                <span className={`font-bold ${temperatureTrend > 0 ? 'text-red-400' :
                  temperatureTrend < 0 ? 'text-emerald-400' :
                    'text-slate-300'
                  }`}>
                  {temperatureTrend > 0 ? '📈 Rising' : temperatureTrend < 0 ? '📉 Declining' : '➡️ Stable'}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className={`rounded-2xl p-6 border-2 ${estimatedRUL && estimatedRUL < 4 ? 'bg-red-500/10 border-red-500' :
          estimatedRUL && estimatedRUL < 8 ? 'bg-amber-500/10 border-amber-500' :
            'bg-slate-800/50 border-slate-700'
          }`}>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">Estimated RUL</p>
          <p className={`text-3xl font-bold mb-1 ${estimatedRUL && estimatedRUL < 4 ? 'text-red-400' :
            estimatedRUL && estimatedRUL < 8 ? 'text-amber-400' :
              'text-sky-400'
            }`}>
            {estimatedRUL ?? '—'}
          </p>
          <p className="text-xs text-slate-400">hours remaining</p>
        </div>
      </div>

      {maintenanceRecommendation && (
        <div className={`rounded-2xl p-6 mb-6 border-l-4 ${maintenanceRecommendation.color === 'red' ? 'bg-red-500/10 border-red-500' :
          maintenanceRecommendation.color === 'amber' ? 'bg-amber-500/10 border-amber-500' :
            maintenanceRecommendation.color === 'yellow' ? 'bg-yellow-500/10 border-yellow-500' :
              'bg-emerald-500/10 border-emerald-500'
          }`}>
          <div className="flex items-start gap-3">
            <span className="text-2xl mt-1">🔧</span>
            <div className="flex-1">
              <p className={`font-bold mb-1 ${maintenanceRecommendation.color === 'red' ? 'text-red-400' :
                maintenanceRecommendation.color === 'amber' ? 'text-amber-400' :
                  maintenanceRecommendation.color === 'yellow' ? 'text-yellow-400' :
                    'text-emerald-400'
                }`}>
                {maintenanceRecommendation.severity}: {maintenanceRecommendation.message}
              </p>
            </div>
          </div>
        </div>
      )}

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
        ) : (isFaulty || hasSeenFault) ? (
          <div className="flex items-center gap-4">
            <span className="text-amber-400 text-sm">
              {isFaulty ? 'Active fault detected —' : 'Historical fault detected —'}
            </span>
            <button
              onClick={handleAskAI}
              disabled={explainLoading || !connected}
              className="px-5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-900 font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {explainLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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

      {thresholdFault && (
        <div className="rounded-2xl bg-red-500/10 border-2 border-red-500 p-6 mb-6">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-red-400 uppercase tracking-wider mb-2">
                ⚠️ Physics-Based Fault Detection — Pattern Detected
              </p>
              <p className="text-slate-300 text-sm mb-3">
                <span className="font-semibold">{thresholdFault.faultCount}/{thresholdFault.windowSize}</span> recent readings exceed danger thresholds
              </p>
              <p className="text-slate-200 text-sm mb-3">{thresholdFault.reason}</p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-slate-500">Vibration</p>
                  <p className="text-red-400 font-bold">{thresholdFault.vib} m/s²</p>
                </div>
                <div>
                  <p className="text-slate-500">Temperature</p>
                  <p className="text-red-400 font-bold">{thresholdFault.temp}°C</p>
                </div>
              </div>
            </div>
          </div>

          {faultExplanation ? (
            <div className="flex items-start gap-3 mt-4">
              <span className="text-2xl">🤖</span>
              <div className="flex-1">
                <p className="text-slate-200">{faultExplanation}</p>
                <button
                  onClick={() => setThresholdFault(null)}
                  className="text-xs text-slate-500 hover:text-slate-300 mt-2 underline"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={handleAskAIForThresholdFault}
              disabled={faultExplainLoading || !connected}
              className="w-full mt-4 px-5 py-3 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {faultExplainLoading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Analyzing Fault...
                </>
              ) : 'Ask AI for Fault Analysis'}
            </button>
          )}
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-4">Live Vibration</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 30]} />
                <Tooltip contentStyle={chartTooltipStyle} labelStyle={{ color: '#e2e8f0' }} />
                <Legend />
                <ReferenceLine y={VIB_WARN} stroke="#f59e0b" strokeDasharray="5 5" label={{ value: 'Warning', fill: '#f59e0b', fontSize: 10 }} />
                <ReferenceLine y={VIB_DANGER} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Danger', fill: '#ef4444', fontSize: 10 }} />
                <Line type="monotone" dataKey="vib" name="Vibration" stroke="#38bdf8" strokeWidth={2} dot={false} animationDuration={300} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-4">Live Temperature</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorHistory} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} unit="°C" domain={[0, 100]} />
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2 rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-3">Prediction History</h2>
          <p className="text-xs text-slate-500 mb-3">
            Label readings to improve the model — click the check or X to confirm or correct each prediction.
          </p>
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
                    <th className="text-center py-2 px-3">Feedback</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {predictionHistory.map((entry, i) => (
                    <tr key={i} className="hover:bg-slate-700/30">
                      <td className="py-1.5 px-3 text-slate-400 font-mono text-xs">{entry.time}</td>
                      <td className="py-1.5 px-3">
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${entry.prediction === 'Faulty'
                          ? 'bg-red-500/20 text-red-400'
                          : 'bg-emerald-500/20 text-emerald-400'
                          }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${entry.prediction === 'Faulty' ? 'bg-red-400' : 'bg-emerald-400'
                            }`} />
                          {entry.prediction}
                        </span>
                      </td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{entry.vib ?? '—'}</td>
                      <td className="py-1.5 px-3 text-right text-slate-300">{entry.temp ?? '—'}</td>
                      <td className="py-1.5 px-3 text-center">
                        {entry.feedbackSent ? (
                          <span className="text-xs text-violet-400">
                            {entry.correctedLabel === 1 ? 'Faulty' : 'Healthy'}
                          </span>
                        ) : (
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => handleFeedback(entry, entry.prediction === 'Faulty' ? 1 : 0)}
                              title="Confirm prediction is correct"
                              className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/40 text-xs"
                            >
                              ✓
                            </button>
                            <button
                              onClick={() => handleFeedback(entry, entry.prediction === 'Faulty' ? 0 : 1)}
                              title="Prediction was wrong — flip label"
                              className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/40 text-xs"
                            >
                              ✗
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-2xl bg-slate-800/50 border border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-3">Model Training</h2>
          <p className="text-xs text-slate-500 mb-4">
            Retrain the model using the base AI4I dataset combined with your live sensor readings for true predictive maintenance.
          </p>

          <button
            onClick={handleRetrain}
            disabled={retrainLoading || !connected}
            className="w-full px-4 py-3 rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors mb-4"
          >
            {retrainLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Retraining...
              </span>
            ) : 'Retrain Model'}
          </button>

          {retrainResult && (
            <div className={`rounded-lg p-4 text-sm ${retrainResult.status === 'success'
              ? 'bg-emerald-500/10 border border-emerald-500/30'
              : 'bg-red-500/10 border border-red-500/30'
              }`}>
              {retrainResult.status === 'success' ? (
                <>
                  <p className="text-emerald-400 font-medium mb-2">Model retrained successfully!</p>
                  <div className="space-y-1 text-slate-300 text-xs">
                    <p>Accuracy: <span className="font-mono text-emerald-400">{(retrainResult.accuracy * 100).toFixed(1)}%</span></p>
                    <p>Base samples: <span className="font-mono">{retrainResult.base_count?.toLocaleString()}</span></p>
                    <p>Sensor readings: <span className="font-mono text-violet-400">{retrainResult.history_count?.toLocaleString()}</span></p>
                    <p>Total training data: <span className="font-mono">{retrainResult.total_count?.toLocaleString()}</span></p>
                  </div>
                </>
              ) : (
                <p className="text-red-400">{retrainResult.message || 'Retrain failed.'}</p>
              )}
            </div>
          )}
        </div>
      </div>

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