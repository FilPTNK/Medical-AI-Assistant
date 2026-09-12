import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { installAuthFetch } from './lib/apiClient'

// Phông NHÚNG THẲNG vào bản dựng, không tải từ Google Fonts. Phòng khám có thể
// mất mạng, và khi đó chữ sẽ nhảy sang phông dự phòng ngay giữa lúc đang khám.
// Be Vietnam Pro được thiết kế cho tiếng Việt — Figtree mà ui-ux-pro-max đề
// xuất KHÔNG có dấu tiếng Việt, dùng nó là mọi chữ có dấu rơi sang phông khác.
import '@fontsource/be-vietnam-pro/400.css'
import '@fontsource/be-vietnam-pro/500.css'
import '@fontsource/be-vietnam-pro/600.css'
import '@fontsource/be-vietnam-pro/700.css'

import './index.css'

// Vá fetch trước khi React render: mọi lệnh gọi /api/ trong App tự mang theo
// session token, và phản hồi 401 sẽ đưa người dùng về màn hình đăng nhập.
installAuthFetch()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
