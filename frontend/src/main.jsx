import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { installAuthFetch } from './lib/apiClient'
import './index.css'

// Vá fetch trước khi React render: mọi lệnh gọi /api/ trong App tự mang theo
// session token, và phản hồi 401 sẽ đưa người dùng về màn hình đăng nhập.
installAuthFetch()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
