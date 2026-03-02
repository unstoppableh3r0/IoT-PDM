// Optional: MQTT.js needs global in browser
if (typeof window !== 'undefined') window.global = window

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <App />,
)
