import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  MessageSquare, 
  Pill, 
  FileText, 
  Info, 
  Settings, 
  Moon, 
  Sun, 
  History, 
  ChevronLeft, 
  ChevronRight, 
  ChevronUp, 
  ChevronDown, 
  ExternalLink, 
  Copy, 
  ThumbsUp, 
  ThumbsDown, 
  Send, 
  Upload, 
  Trash2, 
  X, 
  CheckCircle2, 
  Loader2, 
  Sparkles, 
  AlertCircle,
  BookOpen
} from 'lucide-react';

export default function App() {
  // Navigation & Page state
  const [activeTab, setActiveTab] = useState('chat'); // 'chat', 'meds', 'docs', 'about', 'settings'
  const [isDarkMode, setIsDarkMode] = useState(() => localStorage.getItem('theme') === 'dark');
  const [showHistoryPopover, setShowHistoryPopover] = useState(false);

  // Core Data State
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [searchHistory, setSearchHistory] = useState([]);
  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('deepseek_api_key') || '');
  const [bannerMessage, setBannerMessage] = useState('');

  // Active Document Reader state
  const [activePage, setActivePage] = useState(null); 
  const [activeSources, setActiveSources] = useState([]);
  const [selectedSourceIndex, setSelectedSourceIndex] = useState(0);

  // Chat message history
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Xin chào! Tôi là Trợ lý Y khoa MedRetrieve. Hãy tải tài liệu y văn dạng PDF của bạn lên mục **Tài liệu**, sau đó đặt câu hỏi tại đây để tôi hỗ trợ tra cứu.',
      time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
    }
  ]);

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  // Suggested queries for Vietnamese UI
  const suggestions = [
    "Tác dụng phụ của paracetamol là gì?",
    "Paracetamol có dùng được cho bà bầu không?",
    "Tương tác thuốc với paracetamol?"
  ];

  // Mock drug database for the "Thuốc" tab
  const mockDrugs = [
    { name: "Paracetamol (Acetaminophen)", class: "Giảm đau, hạ sốt", brand: "Hapacol, Panadol, Efferalgan", desc: "Dùng để hạ sốt và giảm các cơn đau từ nhẹ đến vừa. Cực kỳ lưu ý liều dùng để tránh ngộ độc gan." },
    { name: "Ibuprofen", class: "Kháng viêm phi steroid (NSAID)", brand: "Gofen, Alaxan", desc: "Giảm đau, kháng viêm và hạ sốt. Cần thận trọng ở bệnh nhân loét dạ dày tá tràng." },
    { name: "Amoxicillin", class: "Kháng sinh nhóm Penicillin", brand: "Clamoxyl, Ospamox", desc: "Điều trị các bệnh nhiễm trùng đường hô hấp, tai mũi họng, tiết niệu do vi khuẩn nhạy cảm." },
    { name: "Metformin", class: "Thuốc trị đái tháo đường", brand: "Glucophage, Panfor", desc: "Thuốc đầu tay điều trị đái tháo đường typ 2, giúp tăng nhạy cảm với insulin ở mô ngoại vi." }
  ];

  // Synchronize Dark Mode Class
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkMode]);

  // Load backend documents & search history
  useEffect(() => {
    fetchDocuments();
    const savedHistory = localStorage.getItem('med_search_history');
    if (savedHistory) {
      setSearchHistory(JSON.parse(savedHistory));
    }
  }, []);

  // Sync API warning banner
  useEffect(() => {
    if (!apiKey) {
      setBannerMessage("Cảnh báo: Chưa cấu hình DeepSeek API Key. Hãy nhập key trong mục Cài đặt để sử dụng tính năng AI phản hồi đầy đủ.");
    } else {
      setBannerMessage("");
    }
  }, [apiKey]);

  // Auto-scroll chat window when new messages arrive
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Setup default sources and active reader page on initial load
  useEffect(() => {
    const initialAssistantMsg = messages.find(m => m.role === 'assistant' && m.sources);
    if (initialAssistantMsg) {
      setActiveSources(initialAssistantMsg.sources);
      setSelectedSourceIndex(0);
      setActivePage(initialAssistantMsg.sources[0]);
    }
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await fetch('/api/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data || []);
      } else {
        setDocuments([]);
      }
    } catch (err) {
      console.error("Error fetching documents:", err);
      setDocuments([]);
    }
  };

  const showStatus = (type, text) => {
    setStatusMsg({ type, text });
    setTimeout(() => {
      setStatusMsg({ type: '', text: '' });
    }, 5000);
  };

  const handleSearch = async (searchQuery) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setActiveTab('chat'); // Always redirect to chat view when running search
    setShowHistoryPopover(false);

    // Get timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

    // Append User Message
    const userMsg = { role: 'user', text: q, time: timeStr };
    setMessages(prev => [...prev, userMsg]);
    setQuery('');
    setLoading(true);

    // Save search history
    const updatedHistory = [q, ...searchHistory.filter(item => item !== q)].slice(0, 15);
    setSearchHistory(updatedHistory);
    localStorage.setItem('med_search_history', JSON.stringify(updatedHistory));

    // Call Real Backend APIty",
            page_num: 1,
            text: `Alcohol ingestion induces CYP2E1 enzymes, which shifts acetaminophen metabolism towards the production of NAPQI. In chronic alcoholics, even therapeutic doses of acetaminophen can theoretically pose a higher risk of liver injury, especially during periods of fasting when glutathione stores are depleted.`
          },
          {
            doc_name: "BNF 84: Paracetamol",
            page_num: 45,
            text: `Interactions: Domperidone and metoclopramide increase absorption of paracetamol. Cholestyramine reduces absorption of paracetamol. Long-term regular administration of paracetamol may enhance the anticoagulant effect of warfarin.`
          }
        ]
      };
    }
    return null;
  };

  const handleSearch = async (searchQuery) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setActiveTab('chat'); // Always redirect to chat view when running search
    setShowHistoryPopover(false);

    // Get timestamp
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

    // Append User Message
    const userMsg = { role: 'user', text: q, time: timeStr };
    setMessages(prev => [...prev, userMsg]);
    setQuery('');
    setLoading(true);

    // Save search history
    const updatedHistory = [q, ...searchHistory.filter(item => item !== q)].slice(0, 15);
    setSearchHistory(updatedHistory);
    localStorage.setItem('med_search_history', JSON.stringify(updatedHistory));

    // Call Real Backend API
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (apiKey) {
        headers['X-DeepSeek-Key'] = apiKey;
      }

      const res = await fetch('/api/search', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: q })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Yêu cầu tìm kiếm thất bại.");
      }

      const data = await res.json();
      
      const assistantMsg = {
        role: 'assistant',
        text: data.answer,
        sources: data.sources || [],
        time: timeStr
      };

      setMessages(prev => [...prev, assistantMsg]);
      if (data.sources && data.sources.length > 0) {
        setActiveSources(data.sources);
        setSelectedSourceIndex(0);
        setActivePage(data.sources[0]);
      } else {
        setActiveSources([]);
        setActivePage(null);
      }
    } catch (err) {
      console.error(err);
      const errorMsg = {
        role: 'assistant',
        text: `Lỗi tìm kiếm: ${err.message}\n\n(Vui lòng cấu hình API Key trong trang Cài đặt và thử lại hoặc kiểm tra kết nối mạng.)`,
        sources: [],
        time: timeStr
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      showStatus('error', 'Chỉ hỗ trợ tải lên tài liệu định dạng PDF.');
      return;
    }

    setUploading(true);
    showStatus('info', `Đang xử lý phân tích và chỉ mục hóa tài liệu "${file.name}"...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Tải lên và xử lý tệp thất bại.");
      }

      const data = await res.json();
      showStatus('success', `Tải lên thành công "${file.name}" (${data.pages} trang, ${data.chunks} phân đoạn văn bản)!`);
      fetchDocuments();
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDeleteDoc = async (docName, e) => {
    e.stopPropagation();
    if (!confirm(`Bạn có chắc chắn muốn xóa chỉ mục của tài liệu "${docName}"?`)) return;

    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}`, {
        method: 'DELETE'
      });

      if (res.ok) {
        showStatus('success', `Đã xóa tài liệu "${docName}".`);
        fetchDocuments();
        if (activePage && activePage.doc_name === docName) {
          setActivePage(null);
        }
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || "Không thể xóa tài liệu.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const handleOpenPageReader = async (docName, pageNum, fallbackSource = null) => {
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}`);
      if (res.ok) {
        const data = await res.json();
        setActivePage(data);
      } else {
        if (fallbackSource) {
          setActivePage(fallbackSource);
        } else {
          const errData = await res.json();
          showStatus('error', errData.detail || "Không thể đọc nội dung trang.");
        }
      }
    } catch (err) {
      if (fallbackSource) {
        setActivePage(fallbackSource);
      } else {
        showStatus('error', "Lỗi kết nối khi tải trang tài liệu.");
      }
    }
  };

  const handlePrevPage = () => {
    if (!activePage) return;
    const prevPage = activePage.page_num - 1;
    if (prevPage < 1) return;
    handleOpenPageReader(activePage.doc_name, prevPage);
  };

  const handleNextPage = () => {
    if (!activePage) return;
    const nextPage = activePage.page_num + 1;
    const docInfo = documents.find(d => d.doc_name === activePage.doc_name);
    const maxPage = docInfo ? docInfo.page_count : 1698;
    if (nextPage > maxPage) return;
    handleOpenPageReader(activePage.doc_name, nextPage);
  };

  const handleSaveApiKey = (e) => {
    e.preventDefault();
    localStorage.setItem('deepseek_api_key', apiKey);
    showStatus('success', 'Đã cập nhật DeepSeek API Key thành công!');
  };

  const clearHistory = () => {
    setSearchHistory([]);
    localStorage.removeItem('med_search_history');
    showStatus('info', 'Đã xóa lịch sử tìm kiếm.');
    setShowHistoryPopover(false);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    showStatus('success', 'Đã sao chép nội dung vào bộ nhớ tạm.');
  };

  const renderSimpleMarkdown = (text) => {
    if (!text) return null;
    const lines = text.split('\n');
    return lines.map((line, lineIdx) => {
      let content = line;
      
      const isBullet = line.trim().startsWith('*') || line.trim().startsWith('-');
      if (isBullet) {
        content = line.trim().substring(1).trim();
      }
      
      const boldRegex = /\*\*(.*?)\*\*/g;
      const parts = content.split(boldRegex);
      const parsedLine = parts.map((part, partIdx) => {
        if (partIdx % 2 === 1) {
          return <strong key={partIdx}>{part}</strong>;
        }
        return part;
      });
      
      if (isBullet) {
        return (
          <ul key={lineIdx} className="markdown-bullet-list">
            <li>{parsedLine}</li>
          </ul>
        );
      }
      
      if (line.startsWith('**') && line.endsWith('**')) {
        const headingText = line.replace(/\*\*/g, '');
        return <h4 key={lineIdx} className="markdown-heading">{headingText}</h4>;
      }
      
      return <p key={lineIdx} className="markdown-paragraph">{parsedLine}</p>;
    });
  };

  const renderMessageText = (text, sources) => {
    if (!text) return '';
    const regex = /\[(\d+)\]/g;
    const parts = text.split(regex);
    
    return parts.map((part, idx) => {
      if (idx % 2 === 1) {
        const num = parseInt(part, 10);
        const source = sources?.[num - 1];
        
        let badgeClass = 'citation-badge-1';
        if (num === 2) badgeClass = 'citation-badge-2';
        else if (num === 3) badgeClass = 'citation-badge-3';
        else if (num === 4) badgeClass = 'citation-badge-4';
        
        return (
          <button
            key={idx}
            className={`citation-badge ${badgeClass}`}
            onClick={() => {
              if (source) {
                setSelectedSourceIndex(num - 1);
                handleOpenPageReader(source.doc_name, source.page_num, source);
              }
            }}
            title={source ? `${source.doc_name} - Trang ${source.page_num}` : `Nguồn ${num}`}
          >
            {num}
          </button>
        );
      }
      return renderSimpleMarkdown(part);
    });
  };

  return (
    <div className="desktop-layout">
      {/* 1. Left Vertical Navigation Sidebar */}
      <aside className="left-sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo">
            <Pill size={22} className="logo-icon" />
          </div>
        </div>
        <nav className="sidebar-nav">
          <button 
            className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
            title="Trò chuyện"
          >
            <MessageSquare size={22} />
            <span>Chat</span>
          </button>
          <button 
            className={`nav-item ${activeTab === 'meds' ? 'active' : ''}`}
            onClick={() => setActiveTab('meds')}
            title="Thuốc"
          >
            <Pill size={22} />
            <span>Thuốc</span>
          </button>
          <button 
            className={`nav-item ${activeTab === 'docs' ? 'active' : ''}`}
            onClick={() => setActiveTab('docs')}
            title="Tài liệu"
          >
            <FileText size={22} />
            <span>Tài liệu</span>
          </button>
          <button 
            className={`nav-item ${activeTab === 'about' ? 'active' : ''}`}
            onClick={() => setActiveTab('about')}
            title="Giới thiệu"
          >
            <Info size={22} />
            <span>Giới thiệu</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <button 
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
            title="Cài đặt"
          >
            <Settings size={22} />
            <span>Cài đặt</span>
          </button>
        </div>
      </aside>

      {/* 2. Main Content Workspace */}
      <div className="main-workspace">
        {/* Top Header Bar */}
        <header className="workspace-header">
          <div className="header-info">
            <div className="brand-title-row">
              <h1>MedRAG Assistant</h1>
              <span className="badge-beta">Beta</span>
            </div>
            <p className="brand-subtitle">Tra cứu thông tin thuốc dựa trên tài liệu y khoa đáng tin cậy</p>
          </div>
          <div className="header-actions">
            {/* Lịch sử hội thoại Button */}
            <div className="popover-wrapper">
              <button 
                className="btn-history-toggle"
                onClick={() => setShowHistoryPopover(!showHistoryPopover)}
              >
                <History size={16} />
                <span>Lịch sử hội thoại</span>
              </button>
              
              {showHistoryPopover && (
                <div className="history-popover">
                  <div className="popover-header">
                    <h3>Recent Searches</h3>
                    {searchHistory.length > 0 && (
                      <button onClick={clearHistory} className="btn-clear-history">Clear all</button>
                    )}
                  </div>
                  <div className="popover-content">
                    {searchHistory.length === 0 ? (
                      <div className="popover-empty">Chưa có lịch sử câu hỏi.</div>
                    ) : (
                      searchHistory.map((h, idx) => (
                        <button 
                          key={idx} 
                          className="popover-item"
                          onClick={() => handleSearch(h)}
                        >
                          <Search size={12} className="item-icon" />
                          <span className="item-text">{h}</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Dark Mode Toggle */}
            <button 
              className="btn-theme-toggle"
              onClick={() => setIsDarkMode(!isDarkMode)}
              title={isDarkMode ? "Chuyển sang Giao diện Sáng" : "Chuyển sang Giao diện Tối"}
            >
              {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
            </button>
          </div>
        </header>

        {/* Global Toast Alert Banners */}
        {bannerMessage && (
          <div className="alert-banner warning-banner">
            <AlertCircle size={16} />
            <span>{bannerMessage}</span>
          </div>
        )}

        {statusMsg.text && (
          <div className={`alert-banner status-${statusMsg.type}`}>
            {statusMsg.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Page / Tab Content Area */}
        <div className="workspace-body">
          {/* TAB 1: Chat Dashboard (Split View) */}
          {activeTab === 'chat' && (
            <div className="chat-dashboard-split">
              {/* Left Column: Chat Area */}
              <div className="chat-panel">
                <div className="panel-header">
                  <MessageSquare size={18} className="panel-header-icon" />
                  <h2>Trò chuyện</h2>
                </div>

                {/* Conversation Scroller */}
                <div className="chat-messages-container">
                  {messages.map((msg, index) => (
                    <div key={index} className={`message-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}>
                      {msg.role === 'assistant' && (
                        <div className="assistant-avatar">
                          <Sparkles size={16} className="avatar-spark" />
                        </div>
                      )}
                      <div className="message-bubble">
                        <div className="bubble-text">
                          {msg.role === 'assistant' 
                            ? renderMessageText(msg.text, msg.sources) 
                            : <p className="markdown-paragraph">{msg.text}</p>
                          }
                        </div>
                        <div className="bubble-footer">
                          {msg.role === 'assistant' && (
                            <div className="bubble-actions">
                              <button onClick={() => copyToClipboard(msg.text)} title="Sao chép câu trả lời">
                                <Copy size={13} />
                              </button>
                              <button title="Hữu ích">
                                <ThumbsUp size={13} />
                              </button>
                              <button title="Không hữu ích">
                                <ThumbsDown size={13} />
                              </button>
                            </div>
                          )}
                          <span className="bubble-time">{msg.time}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="message-row row-assistant">
                      <div className="assistant-avatar">
                        <Loader2 className="avatar-spark animate-spin" size={16} />
                      </div>
                      <div className="message-bubble bubble-loading">
                        <div className="loading-dots">
                          <span />
                          <span />
                          <span />
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Suggestion Chips */}
                <div className="chat-suggestions-container">
                  {suggestions.map((s, idx) => (
                    <button 
                      key={idx} 
                      className="btn-suggestion-chip"
                      onClick={() => handleSearch(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>

                {/* Chat Input Area */}
                <form 
                  onSubmit={(e) => { e.preventDefault(); handleSearch(); }}
                  className="chat-input-container"
                >
                  <div className="input-row">
                    <textarea 
                      className="input-textarea"
                      placeholder="Nhập câu hỏi của bạn..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSearch();
                        }
                      }}
                    />
                    <button type="submit" className="btn-send" disabled={loading || !query.trim()}>
                      <Send size={16} />
                    </button>
                  </div>
                  <div className="input-footer">
                    <CheckCircle2 size={14} className="checkmark-icon" />
                    <span>Nguồn: Tài liệu y khoa đáng tin cậy</span>
                  </div>
                </form>
              </div>

              {/* Right Column: References & Reader */}
              <div className="reference-panel">
                {/* Reference list */}
                <div className="citation-list-card">
                  <div className="card-header">
                    <div className="card-header-left">
                      <BookOpen size={18} className="header-icon-blue" />
                      <h2>Trích dẫn</h2>
                      {activeSources.length > 0 && (
                        <span className="citation-count-badge">{activeSources.length}</span>
                      )}
                    </div>
                  </div>
                  <div className="card-subtitle">
                    Các nguồn thông tin được trích dẫn trong câu trả lời
                  </div>
                  <div className="citation-items-list">
                    {activeSources.length === 0 ? (
                      <div className="citation-list-empty">Chưa có tài liệu trích dẫn nào được chọn.</div>
                    ) : (
                      activeSources.map((src, idx) => {
                        const isSelected = idx === selectedSourceIndex;
                        let badgeClass = 'citation-badge-1';
                        if (idx === 1) badgeClass = 'citation-badge-2';
                        else if (idx === 2) badgeClass = 'citation-badge-3';
                        else if (idx === 3) badgeClass = 'citation-badge-4';

                        return (
                          <div 
                            key={idx}
                            className={`citation-item-row ${isSelected ? 'selected' : ''}`}
                            onClick={() => {
                              setSelectedSourceIndex(idx);
                              handleOpenPageReader(src.doc_name, src.page_num, src);
                            }}
                          >
                            <div className="item-row-left">
                              <span className={`item-square-badge ${badgeClass}`}>{idx + 1}</span>
                              <div className="item-details">
                                <h3 className="doc-title">{src.doc_name}</h3>
                                <p className="doc-publisher">
                                  {src.doc_name.includes("Dược thư") ? "Bộ Y tế" : 
                                   src.doc_name.includes("Hướng dẫn") ? "Cục Quản lý Dược" : 
                                   src.doc_name.includes("Overdose") ? "UpToDate" : "British National Formulary"}
                                </p>
                              </div>
                            </div>
                            <div className="item-row-right">
                              <span className="doc-page-no">Trang {src.page_num}</span>
                              {isSelected ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Reader Viewer Card */}
                {activePage && (
                  <div className="document-reader-card">
                    <div className="card-header">
                      <h3 className="reader-doc-title">
                        {activePage.doc_name} - Trang {activePage.page_num}
                      </h3>
                      <div className="reader-header-actions">
                        <button className="icon-btn-action" title="Mở trong cửa sổ mới">
                          <ExternalLink size={16} />
                        </button>
                        <button className="icon-btn-action" onClick={() => setActivePage(null)} title="Đóng bảng đọc">
                          <X size={16} />
                        </button>
                      </div>
                    </div>
                    <div className="reader-content-body">
                      {renderSimpleMarkdown(activePage.text)}
                    </div>
                    <div className="reader-footer-pagination">
                      <button onClick={handlePrevPage} disabled={activePage.page_num <= 1}>
                        <ChevronLeft size={16} />
                      </button>
                      <span className="pagination-text">
                        {activePage.page_num} / {
                          documents.find(d => d.doc_name === activePage.doc_name)?.page_count || 1698
                        }
                      </span>
                      <button onClick={handleNextPage}>
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: Thuốc (Medications Index) */}
          {activeTab === 'meds' && (
            <div className="meds-tab-view animate-fade-in">
              <div className="view-header">
                <h2>Cơ sở dữ liệu Thuốc</h2>
                <p>Thông tin tóm tắt và chỉ dẫn lâm sàng nhanh cho thuốc thông dụng</p>
              </div>
              <div className="meds-grid">
                {mockDrugs.map((med, idx) => (
                  <div key={idx} className="med-card">
                    <div className="med-card-header">
                      <h3>{med.name}</h3>
                      <span className="med-class-badge">{med.class}</span>
                    </div>
                    <div className="med-card-body">
                      <p className="med-brand-row"><strong>Biệt dược phổ biến:</strong> {med.brand}</p>
                      <p className="med-desc">{med.desc}</p>
                    </div>
                    <div className="med-card-actions">
                      <button className="btn-search-med" onClick={() => handleSearch(`${med.name} có tác dụng gì và liều dùng như thế nào?`)}>
                        <Search size={14} style={{ marginRight: '6px' }} /> Tra cứu thông tin đầy đủ
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: Tài liệu (Document Management & Upload) */}
          {activeTab === 'docs' && (
            <div className="docs-tab-view animate-fade-in">
              <div className="view-header">
                <h2>Thư viện Tài liệu Đã chỉ mục</h2>
                <p>Quản lý các tài liệu y văn được dùng để trả lời câu hỏi chuyên môn</p>
              </div>

              <div className="docs-grid-layout">
                {/* Upload Card */}
                <div className="upload-card">
                  <h3>Tải lên Tài liệu PDF mới</h3>
                  <p>Hệ thống tự động phân tách trang, trích xuất văn bản và chỉ mục hóa vào cơ sở dữ liệu vector cục bộ.</p>
                  
                  <div 
                    className="upload-dropzone"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload size={32} className="upload-cloud-icon" />
                    <p className="dropzone-text">{uploading ? "Đang xử lý tải lên..." : "Kéo thả hoặc nhấp chọn tệp PDF tại đây"}</p>
                    <span className="dropzone-sub">Kích thước tối đa: 50MB</span>
                    <input 
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      accept=".pdf"
                      style={{ display: 'none' }}
                      disabled={uploading}
                    />
                  </div>
                  {uploading && (
                    <div className="upload-progress-row">
                      <Loader2 className="animate-spin text-blue-500" size={16} />
                      <span>Đang phân tích cú pháp & vector hóa văn bản...</span>
                    </div>
                  )}
                </div>

                {/* Document Library Card */}
                <div className="library-card">
                  <div className="library-header-row">
                    <h3>Thư viện tài liệu ({documents.length})</h3>
                  </div>
                  
                  <div className="library-document-list">
                    {documents.map((doc, idx) => (
                      <div key={idx} className="library-doc-item">
                        <div className="doc-item-details">
                          <h4 title={doc.doc_name}>{doc.doc_name}</h4>
                          <span>{doc.page_count} trang • {doc.chunk_count} phân đoạn văn bản</span>
                        </div>
                        <button 
                          className="btn-delete-doc"
                          onClick={(e) => handleDeleteDoc(doc.doc_name, e)}
                          title="Xóa tài liệu khỏi hệ thống"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: Giới thiệu */}
          {activeTab === 'about' && (
            <div className="about-tab-view animate-fade-in">
              <div className="about-card">
                <h2>Về MedRAG Assistant</h2>
                <p className="intro-lead">Hệ thống trợ lý y tế thông minh ứng dụng công nghệ RAG (Retrieval-Augmented Generation) tiên tiến.</p>
                
                <div className="about-features-grid">
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Truy vấn ngữ nghĩa chính xác</h4>
                      <p>Tìm kiếm và lọc các trang tài liệu y văn có độ khớp ý nghĩa cao nhất với câu hỏi chuyên môn của bác sĩ.</p>
                    </div>
                  </div>
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Đối chiếu nguồn gốc rõ ràng</h4>
                      <p>Tất cả các khẳng định của AI đều bắt buộc kèm số trích dẫn chỉ thẳng đến số trang và tên sách gốc để bác sĩ kiểm chứng.</p>
                    </div>
                  </div>
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Chạy cục bộ an toàn dữ liệu</h4>
                      <p>Hệ thống vector hóa chạy hoàn toàn trên máy cục bộ của người dùng, đảm bảo bảo mật thông tin y khoa tối đa.</p>
                    </div>
                  </div>
                </div>

                <div className="about-system-specs">
                  <h3>Thông tin hệ thống</h3>
                  <ul>
                    <li><strong>Mô hình ngôn ngữ lớn (LLM):</strong> DeepSeek Chat (thông qua API)</li>
                    <li><strong>Mô hình trích xuất vector:</strong> all-MiniLM-L6-v2 (chạy cục bộ dưới nền)</li>
                    <li><strong>Cơ sở dữ liệu vector:</strong> NumPy Simple Index / ChromaDB</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: Cài đặt */}
          {activeTab === 'settings' && (
            <div className="settings-tab-view animate-fade-in">
              <div className="settings-card">
                <h2>Cấu hình & Cài đặt hệ thống</h2>
                <p className="card-desc">Thiết lập khóa API truy cập và các thông số hoạt động của MedRAG.</p>

                <form onSubmit={handleSaveApiKey} className="settings-form">
                  <div className="settings-form-group">
                    <label>DeepSeek API Key</label>
                    <input 
                      type="password"
                      className="settings-input"
                      placeholder="Nhập api key sk-..."
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                    />
                    <span className="input-helper-text">Khóa API sẽ được lưu an toàn tại bộ nhớ cục bộ (Local Storage) trên trình duyệt của bạn.</span>
                  </div>
                  <button type="submit" className="btn-save-settings">Lưu Cấu hình</button>
                </form>
              </div>
            </div>
          )}
        </div>

        {/* Universal Footer Banner */}
        <footer className="workspace-footer-bar">
          <span>Thông tin chỉ mang tính chất tham khảo, không thay thế cho chẩn đoán và điều trị của bác sĩ.</span>
        </footer>
      </div>
    </div>
  );
}
