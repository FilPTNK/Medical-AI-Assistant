import React, { useState, useEffect, useRef } from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Dialog from '@radix-ui/react-dialog';
import { AnimatePresence, motion } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github-dark.css';
import { readSseStream } from './lib/sse';
import { findMatches, bestAnchor } from './lib/fold';
import PageViewer from './components/PageViewer';
import AttachmentCard from './components/AttachmentCard';
import ChatDocuments from './components/ChatDocuments';
import NumberCheck from './components/NumberCheck';
import QueryUnderstood from './components/QueryUnderstood';
import CoverageChecklist from './components/CoverageChecklist';
import Pagination from './components/Pagination';
import DiagnosisTreeView from './components/DiagnosisTreeView';
import { apiJson, apiSend } from './lib/apiClient';
import {
  AlertCircle,
  Activity,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  Eye,
  Globe,
  FileText,
  History,
  Layers,
  Loader2,
  MessageSquare,
  Mic,
  MoreHorizontal,
  Paperclip,
  PencilLine,
  Pin,
  PinOff,
  ScanLine,
  Search,
  Send,
  Share2,
  Sparkles,
  Square,
  SquarePen,
  Stethoscope,
  ThumbsDown,
  Flag,
  ThumbsUp,
  Trash2,
  UserRound,
  X,
} from 'lucide-react';

const uid = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`);

const MAX_PINNED_CONVERSATIONS = 3;
const CHAT_PROMPTS = [
  ['Liều paracetamol trẻ em', 'Cách xác định liều paracetamol cho trẻ em theo tài liệu tham khảo?'],
  ['Tương tác warfarin', 'Những tương tác thuốc nào cần lưu ý khi dùng warfarin?'],
  ['Phác đồ COPD', 'Tra cứu hướng dẫn điều trị COPD ổn định.'],
  ['Chẩn đoán đái tháo đường thai kỳ', 'Tra cứu tiêu chuẩn chẩn đoán đái tháo đường thai kỳ.'],
];

export default function App({ user, settings, clinical, activeTab, onOpenChat }) {
  const { documents, config, conversations, setConversations, apiKey } = clinical;
  const doctorName = user?.display_name || 'Bác sĩ';
  const webSearchTools = config?.web_search_tools || [];
  const goToChat = () => {
    if (activeTab !== 'chat') onOpenChat();
  };
  const [historyOpen, setHistoryOpen] = useState(null);
  const [showAllRecent, setShowAllRecent] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploadFromComposer, setUploadFromComposer] = useState(false);
  const [deleteDocTarget, setDeleteDocTarget] = useState(null);
  const [deletingDocument, setDeletingDocument] = useState(false);
  const activeConversationRef = useRef(null);
  const readerCardRef = useRef(null);
  const readerRequest = useRef(0);
  const draftVersion = useRef(0);
  const toggleHistory = () => setHistoryOpen(value => !(value ?? window.matchMedia('(min-width: 1100px)').matches));

  // Core Data State
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [documentPreview, setDocumentPreview] = useState(null);
  // Reader: mặc định xem TRANG GỐC có tô sáng đoạn trích dẫn (PageViewer);
  // bật cái này để đọc bản chữ OCR thay vì ảnh.
  const [readerShowText, setReaderShowText] = useState(false);
  // Đoạn trích dẫn đang được tô trên trang: { doc_name, page_num, quote }.
  // Chỉ áp cho đúng trang đó — lật sang trang khác thì không tô gì.
  const [readerQuote, setReaderQuote] = useState(null);
  // "Hỏi về tài liệu này": khi khác null, câu hỏi chỉ tra trong tài liệu này.
  // { doc_name, doc_title, page_num }
  const [chatScope, setChatScope] = useState(null);
  // Ô gõ số trang. Giữ riêng với activePage.page_num vì lúc bác sĩ đang gõ "40"
  // trên đường tới "400" thì chưa được nhảy trang.
  const [readerPageInput, setReaderPageInput] = useState('');
  // Tìm chữ TRONG tài liệu.
  const [readerQuery, setReaderQuery] = useState('');
  const [readerMatches, setReaderMatches] = useState(null);   // null = chưa tìm lần nào
  const [readerSearching, setReaderSearching] = useState(false);
  const [readerTruncated, setReaderTruncated] = useState(false);
  // Cụm chữ đang được tô sáng trên trang đang mở. Tách khỏi readerQuery để ô
  // tìm kiếm gõ tiếp không làm nhấp nháy phần tô sáng của kết quả đang đọc.
  const [readerHighlight, setReaderHighlight] = useState('');

  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  // "Tìm thêm trên web": danh sách công cụ máy chủ bật (rỗng = ẩn nút), và lựa
  // chọn của bác sĩ — nhớ theo trình duyệt, mặc định tắt.
  const [webSearchOn, setWebSearchOn] = useState(() => {
    try { return localStorage.getItem('web_search_on') === '1'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem('web_search_on', webSearchOn ? '1' : '0'); } catch { /* chế độ riêng tư */ }
  }, [webSearchOn]);

  // Hierarchical multi-layer decision tree data structure
  const [nodeStatusMap, setNodeStatusMap] = useState({});

  // Active Document Reader state
  const [activePage, setActivePage] = useState(null);
  const [activeSources, setActiveSources] = useState([]);
  const [selectedSourceIndex, setSelectedSourceIndex] = useState(0);
  // Lượt tra (feedback_db) của danh sách nguồn đang mở — để "mở trang" và
  // "Báo sai trang" gắn đúng vào câu hỏi đã sinh ra các trang đó.
  const [activeLogId, setActiveLogId] = useState(null);
  const [wrongPages, setWrongPages] = useState(() => new Set());

  const [isRecording, setIsRecording] = useState(null); // null | 'chat'
  const [micSupported] = useState(() => typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window));
  const recognitionRef = useRef(null);
  const recognitionTargetRef = useRef(null);
  const autoSendAfterDictationRef = useRef(null); // set per-dictation; fires on recognition end
  const chatInputRef = useRef(null);
  // AbortController của lần tra cứu đang chạy. Đóng nó là server ngừng
  // gọi mô hình thật, không phải chỉ giao diện thôi ngóng.
  const searchAbortRef = useRef(null);

  // Diagnosis Tree Pipeline state (3-step agent pipeline: tree -> endoscopy -> final diagnosis)
  const [zoomScale, setZoomScale] = useState(1);
  const [treePanOffset, setTreePanOffset] = useState({ x: 0, y: 0 });
  const [isPanningTree, setIsPanningTree] = useState(false);
  const treeWrapperRef = useRef(null);
  const treeCanvasRef = useRef(null);
  const treePanDragRef = useRef(null);
  const [patientDesc, setPatientDesc] = useState('');
  const [diagnosisTree, setDiagnosisTree] = useState(null); // { patient_summary, root_nodes } from Call 1
  const [treeLoading, setTreeLoading] = useState(false);
  const [examResult, setExamResult] = useState(null); // { endoscopy_focus, physical_exam_focus, key_signs_to_look_for } from Call 2
  const [examLoading, setExamLoading] = useState(false);
  const [examNotes, setExamNotes] = useState('');
  const [finalDiagnoses, setFinalDiagnoses] = useState([]); // from Call 3
  const [finalLoading, setFinalLoading] = useState(false);
  const [selectedDiagnosisDetail, setSelectedDiagnosisDetail] = useState(null);
  // Which of the Top-10 the doctor picked to actually hand off to the patient record — the
  // "Cập nhật bệnh" button no longer sends the whole list, only what's checked here.
  const [selectedDiagnosisIds, setSelectedDiagnosisIds] = useState(new Set());
  const [isPreparingHandoff, setIsPreparingHandoff] = useState(false);

  // Keep follow-up requests tied to the description used to generate this tree.
  const [submittedPatientDesc, setSubmittedPatientDesc] = useState('');
  const [allergyCheck, setAllergyCheck] = useState(null);
  // Gợi ý điều trị cho các chẩn đoán bác sĩ đã chọn, hiện ngay trong tab Chẩn đoán.
  const [treatmentResult, setTreatmentResult] = useState(null);

  // Multi-conversation state (ChatGPT-style): each conversation is its own thread with
  // a title, message list, and pin flag. Conversations persist to localStorage.
  const [activeConversationId, setActiveConversationId] = useState(null); // null = draft "new chat", not yet in the list
  const [renamingConvId, setRenamingConvId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const [shareDialog, setShareDialog] = useState(null); // { url } | null
  const [sharing, setSharing] = useState(false);
  const renameInputRef = useRef(null);

  // Cuộc trò chuyện mới bắt đầu trống — không còn tin nhắn chào mẫu.
  const [draftWelcome, setDraftWelcome] = useState(() => []);

  const activeConversation = conversations.find(c => c.id === activeConversationId) || null;
  const messages = activeConversation ? activeConversation.messages : draftWelcome;

  useEffect(() => {
    if (!activeConversationId || activeConversation) return;
    activeConversationRef.current = null;
    readerRequest.current += 1;
    setActiveConversationId(null);
    setActiveSources([]);
    setActiveLogId(null);
    setActivePage(null);
    setSelectedSourceIndex(0);
  }, [activeConversationId, activeConversation]);

  const chatEndRef = useRef(null);

  const [pinnedOpen, setPinnedOpen] = useState(true);
  const [recentsOpen, setRecentsOpen] = useState(true);

  useEffect(() => {
    if (activeTab !== 'chat') return undefined;
    const onKeyDown = (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 'k') {
        event.preventDefault();
        chatInputRef.current?.focus();
      } else if (key === 'o' && event.shiftKey) {
        event.preventDefault();
        handleNewChat();
      } else if (key === 'b') {
        event.preventDefault();
        toggleHistory();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (loading && activeTab === 'chat') chatEndRef.current?.scrollIntoView({ block: 'nearest' });
  }, [messages, loading, activeTab]);

  // Focus the inline rename input when entering rename mode
  useEffect(() => {
    if (renamingConvId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingConvId]);

  const showStatus = (type, text) => {
    setStatusMsg({ type, text });
    setTimeout(() => {
      setStatusMsg({ type: '', text: '' });
    }, 5000);
  };

  // --- Conversation management (ChatGPT-style: New chat + sidebar list are one and the same) ---

  const createConversationTitle = (text) => {
    const trimmed = text.trim().replace(/\s+/g, ' ');
    return trimmed.length > 42 ? `${trimmed.slice(0, 42)}…` : trimmed;
  };

  // Appends a message to a specific conversation immutably; used for both the user turn and the assistant reply
  const appendMessageToConversation = (convId, message) => {
    setConversations(prev => prev.map(c => (
      c.id === convId ? { ...c, messages: [...c.messages, message], updatedAt: Date.now() } : c
    )));
  };

  /**
   * Sửa tin nhắn CUỐI của một cuộc trò chuyện.
   *
   * Câu trả lời tra cứu y văn về theo luồng, nên bong bóng trả lời được tạo
   * rỗng trước rồi lớn dần. `patch` nhận tin nhắn hiện tại và trả về tin nhắn
   * mới, chứ không phải một object trộn vào — nối chữ cần đọc giá trị cũ, và
   * đọc nó từ state bên ngoài sẽ lấy phải bản cũ giữa lúc các mẩu chữ về dồn.
   */
  const patchLastMessage = (convId, patch) => {
    setConversations(prev => prev.map(c => {
      if (c.id !== convId || c.messages.length === 0) return c;
      const messages = c.messages.slice();
      messages[messages.length - 1] = patch(messages[messages.length - 1]);
      return { ...c, messages, updatedAt: Date.now() };
    }));
  };

  /** Gửi một nhãn phản hồi; lỗi mạng thì bỏ qua — đây là đo lường, không chặn bác sĩ. */
  const sendFeedback = (logId, kind, sourceIndex = null) => {
    if (!logId) return Promise.resolve(false);
    return fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_id: logId, kind, source_index: sourceIndex }),
    }).then(r => r.ok).catch(() => false);
  };

  const rateMessage = (convId, index, rating) => {
    const conv = conversations.find(c => c.id === convId);
    const msg = conv?.messages[index];
    if (!msg?.logId) return;
    const next = msg.rating === rating ? null : rating;
    setConversations(prev => prev.map(c => {
      if (c.id !== convId) return c;
      const messages = c.messages.slice();
      messages[index] = { ...messages[index], rating: next };
      return { ...c, messages };
    }));
    if (next) sendFeedback(msg.logId, next);
  };

  const reportWrongPage = () => {
    const key = `${activeLogId}:${selectedSourceIndex}`;
    if (!activeLogId || wrongPages.has(key)) return;
    sendFeedback(activeLogId, 'wrong_page', selectedSourceIndex).then(ok => {
      if (!ok) return;
      setWrongPages(prev => new Set(prev).add(key));
      showStatus('success', 'Đã ghi nhận: trang này không đúng câu hỏi.');
    });
  };

  const handleNewChat = () => {
    draftVersion.current += 1;
    setChatScope(null);
    if (!window.matchMedia('(min-width: 1100px)').matches) setHistoryOpen(false);
    activeConversationRef.current = null;
    readerRequest.current += 1;
    setActiveConversationId(null);
    setDraftWelcome([]);
    setActiveSources([]);
    setActiveLogId(null);
    setActivePage(null);
    setSelectedSourceIndex(0);
    setQuery('');
    goToChat();
  };

  const handleSelectConversation = (id) => {
    if (renamingConvId === id) return; // don't switch away while editing the title
    if (id !== activeConversationRef.current) {
      draftVersion.current += 1;
      setChatScope(null);
      setQuery('');
    }
    activeConversationRef.current = id;
    readerRequest.current += 1;
    setActiveConversationId(id);
    if (!window.matchMedia('(min-width: 1100px)').matches) setHistoryOpen(false);
    goToChat();
    const conv = conversations.find(c => c.id === id);
    const lastWithSources = conv ? [...conv.messages].reverse().find(m => m.sources && m.sources.length > 0) : null;
    if (lastWithSources) {
      setActiveSources(lastWithSources.sources);
      setActiveLogId(lastWithSources.logId || null);
      setSelectedSourceIndex(0);
    } else {
      setActiveSources([]);
      setActiveLogId(null);
    }
    setActivePage(null);
  };

  const handleTogglePin = (id) => {
    setConversations(prev => {
      const conv = prev.find(c => c.id === id);
      if (!conv) return prev;
      if (!conv.pinned) {
        const pinnedCount = prev.filter(c => c.pinned).length;
        if (pinnedCount >= MAX_PINNED_CONVERSATIONS) {
          showStatus('info', `Chỉ có thể ghim tối đa ${MAX_PINNED_CONVERSATIONS} cuộc trò chuyện.`);
          return prev;
        }
      }
      return prev.map(c => (c.id === id ? { ...c, pinned: !c.pinned } : c));
    });
  };

  const startRenameConversation = (conv) => {
    setRenamingConvId(conv.id);
    setRenameDraft(conv.title);
  };

  const commitRenameConversation = () => {
    if (renamingConvId) {
      const trimmed = renameDraft.trim();
      if (trimmed) {
        setConversations(prev => prev.map(c => (c.id === renamingConvId ? { ...c, title: trimmed } : c)));
      }
    }
    setRenamingConvId(null);
    setRenameDraft('');
  };

  const cancelRenameConversation = () => {
    setRenamingConvId(null);
    setRenameDraft('');
  };

  const confirmDeleteConversation = () => {
    if (!deleteTargetId) return;
    setConversations(prev => prev.filter(c => c.id !== deleteTargetId));
    if (activeConversationId === deleteTargetId) {
      handleNewChat();
    }
    setDeleteTargetId(null);
    showStatus('success', 'Đã xóa cuộc trò chuyện.');
  };

  const handleShareConversation = async (conv) => {
    setSharing(true);
    try {
      const res = await fetch('/api/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: conv.title,
          messages: conv.messages.map(m => ({ role: m.role, text: m.text, time: m.time, sources: m.sources || null }))
        })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Không thể tạo liên kết chia sẻ.");
      }
      const data = await res.json();
      const url = `${window.location.origin}/?share=${data.id}`;
      setShareDialog({ url });
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      setSharing(false);
    }
  };

  const renderConvItem = (conv) => (
        <motion.div
          key={conv.id}
          layout
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.16 }}
          className={`conv-item ${conv.id === activeConversationId ? 'active' : ''}`}
        >
                    {renamingConvId === conv.id ? (
            <input
              ref={renameInputRef}
              className="conv-item-rename-input"
              value={renameDraft}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setRenameDraft(e.target.value)}
              onBlur={commitRenameConversation}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitRenameConversation(); }
                else if (e.key === 'Escape') { e.preventDefault(); cancelRenameConversation(); }
              }}
            />
          ) : (
            <button type="button" className="conv-item-title fil-conv-select" title={conv.title}
              onClick={() => handleSelectConversation(conv.id)} aria-current={conv.id === activeConversationId ? 'true' : undefined}>
              {conv.pinned ? <Pin size={15} aria-hidden="true" /> : <MessageSquare size={15} aria-hidden="true" />}
              <span><strong>{conv.title}</strong>{conv.updatedAt && <small>{new Date(conv.updatedAt).toLocaleString('vi-VN', {
                dateStyle: 'short', timeStyle: 'short',
              })}</small>}</span>
            </button>
          )}

          {renamingConvId !== conv.id && (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button" className="conv-item-menu-btn"
                  onClick={(e) => e.stopPropagation()}
                  title="Tùy chọn cuộc trò chuyện"
                >
                  <MoreHorizontal size={15} />
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  className="dropdown-menu-content"
                  align="start"
                  sideOffset={4}
                  onClick={(e) => e.stopPropagation()}
                >
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleTogglePin(conv.id)}>
                    {conv.pinned ? <PinOff size={14} /> : <Pin size={14} />}
                    {conv.pinned ? 'Bỏ ghim' : 'Ghim'}
                  </DropdownMenu.Item>
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => startRenameConversation(conv)}>
                    <PencilLine size={14} />
                    Đổi tên
                  </DropdownMenu.Item>
                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleShareConversation(conv)}>
                    <Share2 size={14} />
                    Chia sẻ
                  </DropdownMenu.Item>
                  <DropdownMenu.Separator className="dropdown-menu-separator" />
                  <DropdownMenu.Item
                    className="dropdown-menu-item danger"
                    onSelect={() => setDeleteTargetId(conv.id)}
                  >
                    <Trash2 size={14} />
                    Xóa
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          )}
        </motion.div>
  );

  // Chat search (uses LLM) — creates a new conversation on the first message of a draft chat
  const handleSearch = async (searchQuery) => {
    const q = searchQuery || query;
    if (!q.trim() || searchAbortRef.current) return;

    goToChat();

    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    // Tài liệu đính kèm thuộc về CÂU HỎI NÀY (như ChatGPT): gửi xong thì thẻ
    // trong ô nhập biến mất, còn tin nhắn đã gửi giữ thẻ để biết câu nào hỏi
    // riêng trong sách nào.
    const attachment = chatScope;
    draftVersion.current += 1;
    readerRequest.current += 1;
    setActiveSources([]);
    setActivePage(null);
    setActiveLogId(null);
    const userMsg = { role: 'user', text: q, time: timeStr, ...(attachment ? { attachment } : {}) };
    setChatScope(null);

    let convId = activeConversationId;
    if (!convId) {
      convId = uid();
      const newConversation = {
        id: convId,
        title: createConversationTitle(q),
        messages: [userMsg],
        pinned: false,
        createdAt: Date.now(),
        updatedAt: Date.now()
      };
      setConversations(prev => [newConversation, ...prev]);
      activeConversationRef.current = convId;
      setActiveConversationId(convId);
    } else {
      appendMessageToConversation(convId, userMsg);
    }

    setQuery('');
    setLoading(true);

    // Bong bóng trả lời được tạo NGAY, còn rỗng, rồi lớn dần theo luồng. Nhờ
    // vậy khối trích dẫn hiện lên trước khi mô hình nói được chữ nào — đo được
    // nguồn về sau ~80ms còn chữ đầu tiên sau ~890ms.
    appendMessageToConversation(convId, {
      role: 'assistant',
      text: '',
      sources: [],
      time: timeStr,
      streaming: true
    });

    const controller = new AbortController();
    searchAbortRef.current = controller;

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (apiKey) {
        headers['X-DeepSeek-Key'] = apiKey;
      }

      const res = await fetch('/api/search', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          query: q,
          created_by: doctorName,
          web: webSearchOn && webSearchTools.length > 0,
          doc_name: attachment?.doc_name || null,
          near_page: attachment?.page_num || null,
        }),
        signal: controller.signal
      });

      if (!res.ok) {
        // Lỗi trước khi luồng bắt đầu (401, 400) vẫn là JSON như cũ.
        let detail = 'Yêu cầu tìm kiếm thất bại.';
        try {
          const errorData = await res.json();
          detail = errorData.detail || detail;
        } catch { /* thân không phải JSON: giữ câu mặc định */ }
        throw new Error(detail);
      }

      await readSseStream(res, (event, data) => {
        if (event === 'status') {
          patchLastMessage(convId, m => ({ ...m, statusNote: data.message }));
        } else if (event === 'sources') {
          const sources = data.sources || [];
          patchLastMessage(convId, m => ({ ...m, sources, statusNote: null }));
          if (activeConversationRef.current === convId) {
            setActiveLogId(null);
            setActiveSources(sources);
            setSelectedSourceIndex(0);
            setActivePage(null);
          }
        } else if (event === 'query_normalized') {
          patchLastMessage(convId, m => ({ ...m, normalized: data }));
        } else if (event === 'query_understood') {
          patchLastMessage(convId, m => ({ ...m, understood: data }));
        } else if (event === 'coverage') {
          patchLastMessage(convId, m => ({ ...m, coverage: data.items || [] }));
        } else if (event === 'verify') {
          patchLastMessage(convId, m => ({ ...m, verify: data }));
        } else if (event === 'done') {
          if (settings.notifyEnabled && document.visibilityState !== 'visible') {
            clinical.addNotification('Tra cứu y khoa đã hoàn tất.');
          }
          if (data.log_id) {
            patchLastMessage(convId, m => ({ ...m, logId: data.log_id }));
            if (activeConversationRef.current === convId) setActiveLogId(data.log_id);
          }
        } else if (event === 'delta') {
          patchLastMessage(convId, m => ({ ...m, text: m.text + data.text }));
        } else if (event === 'error') {
          // KHÔNG xoá trích dẫn đã nhận. `degraded` nghĩa là các trang sách vẫn
          // dùng được, chỉ phần diễn giải của mô hình là không có — bác sĩ vẫn
          // đọc được sách, đó là điểm quan trọng nhất của cả đợt này.
          patchLastMessage(convId, m => ({
            ...m,
            errorMessage: data.message,
            errorDetail: data.detail || null,
            degraded: !!data.degraded,
            statusNote: null
          }));
        }
      });
    } catch (err) {
      if (err.name === 'AbortError') {
        // Bác sĩ tự bấm dừng. Giữ lại chữ và trích dẫn đã về được.
        patchLastMessage(convId, m => ({ ...m, cancelled: true }));
      } else {
        console.error(err);
        patchLastMessage(convId, m => ({
          ...m,
          errorMessage: err.message,
          degraded: (m.sources || []).length > 0
        }));
      }
    } finally {
      searchAbortRef.current = null;
      patchLastMessage(convId, m => ({ ...m, streaming: false }));
      setLoading(false);
    }
  };

  /** Bác sĩ bấm dừng. Đóng kết nối là server dừng gọi mô hình thật. */
  const handleCancelSearch = () => {
    if (searchAbortRef.current) searchAbortRef.current.abort();
  };

  // AI Drug Lookup (Generates comprehensive clinical report with NotebookLM-style citations)
  const handleDownloadDocument = async (docName) => {
    // PDF sách gốc nặng hàng trăm MB (Dược thư Quyển 1: ~835 MB), nên không fetch về
    // blob như các tệp nhỏ — cả tệp sẽ nằm trong RAM của tab. Để trình duyệt tự
    // stream xuống đĩa qua <a download>, xin một vé dùng một lần thay cho header.
    try {
      const { ticket } = await apiSend(
        `/api/documents/${encodeURIComponent(docName)}/download-ticket`, 'POST'
      );
      const a = document.createElement('a');
      a.href = `/api/documents/${encodeURIComponent(docName)}/download?ticket=${encodeURIComponent(ticket)}`;
      a.download = docName;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      console.error('Error downloading document:', err);
      showStatus('error', err.message || 'Không tải được tệp tài liệu.');
    }
  };

  // Xem sách = ảnh trang PDF gốc (PageViewer tự tải ảnh), không cần lấy text.
  const handleOpenDocumentPreview = (docName, pageNum = 1) => {
    setDocumentPreview({ doc_name: docName, page_num: pageNum });
  };

  // Biên chuyển trang của reader. Số trang trong trích dẫn là số trang IN, mà
  // sách scan có phần bìa/mục lục không đánh số liên tục — body_page_range từ
  // manifest cho biết dải trang in thật, tránh bấm "trang sau" ra trang trống.
  const readerMinPage = (docName) => {
    const range = documents.find(d => d.doc_name === docName)?.body_page_range;
    return Array.isArray(range) ? range[0] : 1;
  };

  const readerMaxPage = (docName) => {
    const doc = documents.find(d => d.doc_name === docName);
    if (Array.isArray(doc?.body_page_range)) return doc.body_page_range[1];
    return doc?.page_count || 0;
  };

  // `quoteToHighlight`: đoạn chunk của kết quả tìm kiếm. Bấm vào trích dẫn thì
  // mở đúng trang VÀ tô sáng sẵn đúng đoạn đó — không bắt bác sĩ tự dò lại bằng
  // mắt trên một trang sách đầy chữ.
  const handleOpenPageReader = async (docName, pageNum, fallbackSource = null, quoteToHighlight = null) => {
    const request = ++readerRequest.current;
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}`);
      if (res.ok) {
        const data = await res.json();
        if (request !== readerRequest.current) return;
        setActivePage(data);
        if (quoteToHighlight) setReaderQuote({ doc_name: docName, page_num: pageNum, quote: quoteToHighlight });
        if (quoteToHighlight) {
          // Neo được thì tô sáng, không neo được thì thôi — thà không tô gì còn
          // hơn tô nhầm chỗ.
          setReaderHighlight(bestAnchor(data.text || '', quoteToHighlight));
        }
      } else {
        if (request !== readerRequest.current) return;
        if (fallbackSource) {
          setActivePage(fallbackSource);
        } else {
          const errData = await res.json();
          showStatus('error', errData.detail || "Không thể đọc nội dung trang.");
        }
      }
    } catch (err) {
      if (request !== readerRequest.current) return;
      if (fallbackSource) {
        setActivePage(fallbackSource);
      } else {
        showStatus('error', "Lỗi kết nối khi tải trang tài liệu.");
      }
    }
  };

  // Nhảy thẳng tới một trang. Trước đợt này muốn tới trang 400 phải bấm mũi tên
  // 399 lần: số trang chỉ là chữ hiển thị, không gõ vào được.
  // Tô sáng cụm đang tìm trên chữ CÒN NGUYÊN DẤU.
  //
  // Neo theo NỘI DUNG chứ không theo vị trí ký tự mà backend trả về: hai bên đọc
  // chữ của trang qua hai đường khác nhau (doc_index gộp theo trang in, endpoint
  // trang đi qua page_map), nên độ lệch một vài ký tự là chuyện có thể xảy ra.
  // Neo theo nội dung thì lệch cũng vẫn tô đúng chỗ, còn neo theo offset thì tô
  // trượt mà không ai biết. Đây cũng là tinh thần của TextQuoteSelector (W3C).
  const renderHighlightedText = (text, query) => {
    if (!text) return null;
    const hits = query ? findMatches(text, query) : [];
    if (hits.length === 0) return <span className="reader-plain-text">{text}</span>;
    const parts = [];
    let cursor = 0;
    hits.forEach((h, i) => {
      if (h.start > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, h.start)}</span>);
      parts.push(<mark key={`m${i}`} className="reader-hit">{text.slice(h.start, h.end)}</mark>);
      cursor = h.end;
    });
    if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>);
    return <span className="reader-plain-text">{parts}</span>;
  };

  // Phạm vi thật sự có trong kho. Lấy từ manifest (trường `coverage`), không
  // viết cứng: Dược thư Quyển 1 dừng ở "A – Hydroxyzin", nên bác sĩ tra
  // Paracetamol sẽ không thấy CHUYÊN LUẬN nào. Không nói ra thì họ kết luận là
  // app hỏng, hoặc tệ hơn, kết luận là không có thuốc đó.
  //
  // Lưu ý: chữ "paracetamol" VẪN xuất hiện trên 27 trang của Quyển 1 (trong mục
  // tương tác của thuốc khác), nên câu chữ phải nói về CHUYÊN LUẬN chứ không
  // phải về "không có chữ nào".
  const indexCoverage = () => documents.filter(d => d.coverage);

  const handleGoToPage = (raw) => {
    if (!activePage) return;
    const n = parseInt(String(raw).trim(), 10);
    if (!Number.isFinite(n)) return;
    const min = readerMinPage(activePage.doc_name);
    const max = readerMaxPage(activePage.doc_name);
    if (n < min || (max && n > max)) {
      showStatus('info', `Tài liệu này chỉ có trang ${min}–${max || '?'}.`);
      return;
    }
    handleOpenPageReader(activePage.doc_name, n);
  };

  // Tìm chữ trong CẢ tài liệu, không chỉ trang đang mở.
  const handleSearchInDoc = async () => {
    if (!activePage || !readerQuery.trim()) return;
    setReaderSearching(true);
    try {
      const res = await fetch(
        `/api/documents/${encodeURIComponent(activePage.doc_name)}/search?q=${encodeURIComponent(readerQuery.trim())}`
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không tìm được trong tài liệu.');
      }
      const data = await res.json();
      setReaderMatches(data.matches || []);
      setReaderTruncated(!!data.truncated);
      setReaderHighlight(readerQuery.trim());
      if ((data.matches || []).length === 0) {
        showStatus('info', 'Không có trang nào chứa cụm này.');
      }
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
      setReaderMatches([]);
    } finally {
      setReaderSearching(false);
    }
  };

  const handlePrevPage = () => {
    if (!activePage) return;
    const prevPage = activePage.page_num - 1;
    if (prevPage < readerMinPage(activePage.doc_name)) return;
    handleOpenPageReader(activePage.doc_name, prevPage);
  };

  const handleNextPage = () => {
    if (!activePage) return;
    const nextPage = activePage.page_num + 1;
    const maxPage = readerMaxPage(activePage.doc_name);
    if (maxPage && nextPage > maxPage) return;
    handleOpenPageReader(activePage.doc_name, nextPage);
  };

  // Số trang vào đường dẫn, để mở lại và chia sẻ được đúng chỗ.
  //
  // replaceState chứ không pushState: mỗi lần lật trang mà đẩy một mục vào lịch
  // sử thì nút Back của trình duyệt biến thành nút lùi-một-trang-sách, và bác sĩ
  // phải bấm 40 lần mới thoát ra được. Cả hai hàm đều KHÔNG phát popstate, nên
  // ghi ở đây không vòng ngược lại thành vòng lặp.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (activePage?.doc_name) {
      urlPageOpened.current = true;
      url.searchParams.set('doc', activePage.doc_name);
      url.searchParams.set('page', String(activePage.page_num));
    } else {
      if (!urlPageOpened.current) return;
      url.searchParams.delete('doc');
      url.searchParams.delete('page');
    }
    window.history.replaceState(null, '', url);
  }, [activePage?.doc_name, activePage?.page_num]);

  // Mở đúng trang khi vào bằng đường dẫn có sẵn. Chỉ chạy một lần, sau khi danh
  // sách tài liệu đã về — cần nó để biết khoảng trang hợp lệ.
  const urlPageOpened = useRef(false);
  useEffect(() => {
    if (urlPageOpened.current || documents.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const doc = params.get('doc');
    const page = parseInt(params.get('page') || '', 10);
    if (doc && Number.isFinite(page)) {
      urlPageOpened.current = true;
      handleOpenPageReader(doc, page);
    }
  }, [documents]);

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    showStatus('success', 'Đã sao chép nội dung vào bộ nhớ tạm.');
  };

  // Voice input via the browser's SpeechRecognition API, shared by the Chat and Thuốc search bars
  useEffect(() => {
    if (!micSupported) return;
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = settings.voiceLang; // Settings → Giọng nói → Ngôn ngữ nhận dạng
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (e) => {
      let transcript = '';
      for (let i = 0; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      if (recognitionTargetRef.current) recognitionTargetRef.current(transcript);
    };
    recognition.onerror = () => setIsRecording(null);
    recognition.onend = () => {
      // Settings → Giọng nói → Tự động gửi sau khi ngừng nói
      if (settings.voiceAutoSend) autoSendAfterDictationRef.current?.();
      setIsRecording(null);
    };

    recognitionRef.current = recognition;
    return () => {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
    };
  }, [micSupported, settings.voiceLang, settings.voiceAutoSend]);

  const handleToggleMic = (targetKey, setter, onDictationEnd) => {
    if (!micSupported || !recognitionRef.current) {
      showStatus('error', 'Trình duyệt của bạn không hỗ trợ ghi âm giọng nói. Vui lòng dùng Google Chrome.');
      return;
    }
    autoSendAfterDictationRef.current = onDictationEnd || null;
    if (isRecording === targetKey) {
      recognitionRef.current.stop();
      setIsRecording(null);
      return;
    }
    if (isRecording) {
      recognitionRef.current.stop();
    }
    recognitionTargetRef.current = setter;
    setter('');
    try {
      recognitionRef.current.start();
      setIsRecording(targetKey);
    } catch (err) {
      // start() throws if already active; ignore since onend/onerror will reset state
    }
  };

  // Diagnosis Tree Pipeline controllers (Call 1: generate tree, cascade Có/Không, Call 2: endoscopy, Call 3: final diagnosis)
  const treeRoot = diagnosisTree ? {
    id: 'root',
    type: 'root',
    label: diagnosisTree.patient_summary || 'Bắt đầu',
    children: diagnosisTree.root_nodes || []
  } : null;

  // Infinite canvas controls for the symptom tree: drag-to-pan + cursor-centered wheel zoom (like NotebookLM's mind map)
  const clampTreeZoom = (value) => Math.min(2.5, Math.max(0.3, value));

  const zoomTreeAroundPoint = (px, py, newScaleRaw) => {
    const newScale = clampTreeZoom(newScaleRaw);
    setZoomScale(prevScale => {
      setTreePanOffset(prevPan => ({
        x: px - (px - prevPan.x) * (newScale / prevScale),
        y: py - (py - prevPan.y) * (newScale / prevScale)
      }));
      return newScale;
    });
  };

  const zoomTreeByDelta = (delta) => {
    const wrapper = treeWrapperRef.current;
    const cx = wrapper ? wrapper.clientWidth / 2 : 0;
    const cy = wrapper ? wrapper.clientHeight / 2 : 0;
    zoomTreeAroundPoint(cx, cy, clampTreeZoom(zoomScale + delta));
  };

  const centerTreeCanvas = (scale) => {
    const wrapper = treeWrapperRef.current;
    const canvas = treeCanvasRef.current;
    setZoomScale(scale);
    if (wrapper && canvas) {
      const wrapperWidth = wrapper.clientWidth;
      const canvasWidth = canvas.scrollWidth;
      setTreePanOffset({
        x: Math.max(20, (wrapperWidth - canvasWidth * scale) / 2),
        y: 30
      });
    } else {
      setTreePanOffset({ x: 0, y: 0 });
    }
  };

  const handleTreeCanvasMouseDown = (e) => {
    if (e.button !== 0) return;
    if (e.target.closest('.decision-node-card, .tree-node-root, button')) return;
    e.preventDefault();
    treePanDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startPanX: treePanOffset.x,
      startPanY: treePanOffset.y
    };
    setIsPanningTree(true);
  };

  // Re-center the canvas whenever a fresh tree arrives from Call 1
  useEffect(() => {
    if (!diagnosisTree) return;
    const frame = requestAnimationFrame(() => centerTreeCanvas(1));
    return () => cancelAnimationFrame(frame);
  }, [diagnosisTree]);

  // Window-level drag tracking so panning keeps working even if the cursor leaves the canvas
  useEffect(() => {
    if (!isPanningTree) return;
    const handleMove = (e) => {
      const drag = treePanDragRef.current;
      if (!drag) return;
      setTreePanOffset({
        x: drag.startPanX + (e.clientX - drag.startX),
        y: drag.startPanY + (e.clientY - drag.startY)
      });
    };
    const handleUp = () => {
      treePanDragRef.current = null;
      setIsPanningTree(false);
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [isPanningTree]);

  // Plain wheel scrolls the page; Ctrl+wheel zooms the symptom tree.
  useEffect(() => {
    const wrapper = treeWrapperRef.current;
    if (!wrapper || !diagnosisTree) return;
    const handleWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const rect = wrapper.getBoundingClientRect();
      zoomTreeAroundPoint(e.clientX - rect.left, e.clientY - rect.top, clampTreeZoom(zoomScale * Math.exp(-e.deltaY * 0.001)));
    };
    wrapper.addEventListener('wheel', handleWheel, { passive: false });
    return () => wrapper.removeEventListener('wheel', handleWheel);
  }, [zoomScale, activeTab, diagnosisTree]);

  // Walks the tree honoring the reveal-on-answer rule: only descends into a branch once it has
  // been explicitly answered — boolean 'yes', a chosen 'choice' option, or a filled 'text' value.
  const collectSymptoms = (node, statusMap) => {
    const confirmed = [];
    const excluded = [];
    const walk = (n) => {
      if (!n) return;
      if (n.type === 'root') {
        (n.children || []).forEach(walk);
        return;
      }
      const answerType = n.answer_type || 'boolean';
      if (answerType === 'choice') {
        const selectedId = statusMap[n.id];
        const option = (n.options || []).find(o => o.id === selectedId);
        if (option) {
          // Natural clinical phrasing (e.g. "Dịch mũi đục, xanh hoặc vàng"), not "label: option".
          confirmed.push(option.note || option.label);
          (option.children || []).forEach(walk);
        }
      } else if (answerType === 'text') {
        const value = (statusMap[n.id] || '').trim();
        if (value) {
          // note_template has a "{value}" placeholder, e.g. "Sổ mũi kéo dài {value}".
          const note = n.note_template ? n.note_template.replace('{value}', value) : `${n.label}: ${value}`;
          confirmed.push(note);
        }
      } else {
        const status = statusMap[n.id];
        if (status === 'yes') {
          confirmed.push(n.confirmed_note || n.label);
          (n.children || []).forEach(walk);
        } else if (status === 'no') {
          excluded.push(n.excluded_note || n.label);
        }
      }
    };
    walk(node);
    return { confirmed, excluded };
  };

  const handleGenerateTree = async () => {
    const description = patientDesc.trim();
    if (!description) return;
    setTreeLoading(true);
    setDiagnosisTree(null);
    setNodeStatusMap({});
    setExamResult(null);
    setExamNotes('');
    setFinalDiagnoses([]);
    setSelectedDiagnosisIds(new Set());
    setTreatmentResult(null);
    setAllergyCheck(null);
    try {
      const res = await fetch('/api/diagnosis-tree/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ description })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Tạo cây chẩn đoán thất bại.");
      }
      const data = await res.json();
      setDiagnosisTree(data);
      setSubmittedPatientDesc(description);
      showStatus('success', "Đã tạo cây chẩn đoán từ mô tả bệnh nhân.");
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
    } finally {
      setTreeLoading(false);
    }
  };

  const handleToggleNodeStatus = (nodeId, status) => {
    setNodeStatusMap(prev => {
      const next = { ...prev };
      if (next[nodeId] === status) {
        delete next[nodeId];
      } else {
        next[nodeId] = status;
      }
      return next;
    });
  };

  // 'choice' nodes: value stored is the selected option's id (toggle off on repeat click)
  const handleSelectNodeOption = (nodeId, optionId) => {
    setNodeStatusMap(prev => {
      const next = { ...prev };
      if (next[nodeId] === optionId) {
        delete next[nodeId];
      } else {
        next[nodeId] = optionId;
      }
      return next;
    });
  };

  // 'text' nodes: value stored is the raw typed string
  const handleSetNodeText = (nodeId, value) => {
    setNodeStatusMap(prev => ({ ...prev, [nodeId]: value }));
  };

  const renderDecisionTreeNode = (node) => {
    if (!node) return null;
    const status = nodeStatusMap[node.id];
    const answerType = node.answer_type || 'boolean';

    // Progressive disclosure (mindmap-style): layer-1 nodes (root's direct children) are always
    // visible; deeper layers only reveal once their parent has been explicitly answered — "Có"
    // for boolean, a picked option for choice. "Không" (or no answer yet) keeps them hidden.
    let hasChildren = false;
    let childrenToRender = [];
    let selectedOption = null;
    if (node.type === 'root') {
      childrenToRender = node.children || [];
      hasChildren = childrenToRender.length > 0;
    } else if (answerType === 'choice') {
      selectedOption = (node.options || []).find(o => o.id === status) || null;
      childrenToRender = selectedOption ? (selectedOption.children || []) : [];
      hasChildren = childrenToRender.length > 0;
    } else if (answerType === 'boolean') {
      childrenToRender = node.children || [];
      hasChildren = status === 'yes' && childrenToRender.length > 0;
    }
    // 'text' nodes are always leaves.

    return (
      <div className="decision-tree-node-wrapper" key={node.id}>
        {node.type === 'root' ? (
          <div className="tree-node-root">
            <div className="root-title">Bắt đầu chẩn đoán</div>
            <div className="root-subtitle">{node.label}</div>
          </div>
        ) : answerType === 'choice' ? (
          <div className={`decision-node-card ${status ? 'active-yes' : ''}`}>
            <div className="card-header-row">
              <Stethoscope size={15} style={{ color: status ? 'var(--primary)' : 'var(--primary)', flexShrink: 0 }} />
              <span className="card-title">{node.label}</span>
            </div>
            {selectedOption?.hypothetical_focus && <span className="card-suggest">{selectedOption.hypothetical_focus}</span>}
            <div className="card-buttons-row card-buttons-row-choice">
              {(node.options || []).map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  className={`card-btn card-btn-choice ${status === opt.id ? 'active-choice' : ''}`}
                  onClick={() => handleSelectNodeOption(node.id, opt.id)}
                >
                  {status === opt.id && <Check size={11} />} {opt.label}
                </button>
              ))}
            </div>
          </div>
        ) : answerType === 'text' ? (
          <div className={`decision-node-card ${(status || '').trim() ? 'active-yes' : ''}`}>
            <div className="card-header-row">
              <Stethoscope size={15} style={{ color: (status || '').trim() ? 'var(--primary)' : 'var(--primary)', flexShrink: 0 }} />
              <span className="card-title">{node.label}</span>
            </div>
            {node.hypothetical_focus && <span className="card-suggest">{node.hypothetical_focus}</span>}
            <input
              type="text"
              className="card-text-input"
              placeholder={node.input_hint || 'Nhập câu trả lời...'}
              value={status || ''}
              onChange={(e) => handleSetNodeText(node.id, e.target.value)}
            />
          </div>
        ) : (
          <div className={`decision-node-card ${status === 'yes' ? 'active-yes' : status === 'no' ? 'active-no' : ''}`}>
            <div className="card-header-row">
              <Stethoscope size={15} style={{ color: status === 'yes' ? '#22c55e' : status === 'no' ? '#ef4444' : 'var(--primary)', flexShrink: 0 }} />
              <span className="card-title">{node.label}</span>
            </div>
            {node.hypothetical_focus && <span className="card-suggest">{node.hypothetical_focus}</span>}
            <div className="card-buttons-row">
              <button
                type="button"
                className={`card-btn ${status === 'yes' ? 'active-yes' : ''}`}
                onClick={() => handleToggleNodeStatus(node.id, 'yes')}
              >
                {status === 'yes' && <Check size={11} />} Có
              </button>
              <button
                type="button"
                className={`card-btn ${status === 'no' ? 'active-no' : ''}`}
                onClick={() => handleToggleNodeStatus(node.id, 'no')}
              >
                {status === 'no' && <X size={11} />} Không
              </button>
            </div>
          </div>
        )}

        {hasChildren && (
          <ul className="decision-tree-children">
            {childrenToRender.map(child => (
              <li key={child.id}>
                {renderDecisionTreeNode(child)}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  const handleSuggestExam = async () => {
    if (!treeRoot) return;
    const { confirmed, excluded } = collectSymptoms(treeRoot, nodeStatusMap);
    if (confirmed.length === 0) {
      showStatus('info', "Vui lòng chọn ít nhất một triệu chứng 'Có' trên cây để tiếp tục.");
      return;
    }

    setExamLoading(true);
    setExamResult(null);
    setExamNotes('');
    setFinalDiagnoses([]);
    setSelectedDiagnosisIds(new Set());
    try {
      const res = await fetch('/api/diagnosis-tree/endoscopy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ confirmed_symptoms: confirmed, excluded_symptoms: excluded,
                               patient_history: submittedPatientDesc || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Gợi ý khám & nội soi thất bại.");
      }
      const data = await res.json();
      setExamResult(data);
      showStatus('success', "Đã có gợi ý khám & nội soi.");
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
    } finally {
      setExamLoading(false);
    }
  };

  const handleFinalDiagnosis = async () => {
    if (!examNotes.trim()) {
      showStatus('info', "Vui lòng nhập kết quả khám lâm sàng & nội soi trước khi chẩn đoán.");
      return;
    }
    const { confirmed, excluded } = collectSymptoms(treeRoot, nodeStatusMap);

    setFinalLoading(true);
    try {
      const res = await fetch('/api/diagnosis-tree/final', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ confirmed_symptoms: confirmed, excluded_symptoms: excluded, exam_notes: examNotes,
                               patient_history: submittedPatientDesc || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Chẩn đoán cuối cùng thất bại.");
      }
      const data = await res.json();
      setFinalDiagnoses(data.diagnoses || []);
      setSelectedDiagnosisIds(new Set());
      showStatus('success', "Đã có kết quả chẩn đoán cuối cùng.");
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
    } finally {
      setFinalLoading(false);
    }
  };

  const handleToggleDiagnosisSelected = (idx) => {
    setSelectedDiagnosisIds(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // "Gợi ý điều trị" — phác đồ gợi ý cho các chẩn đoán bác sĩ đã chọn, kèm đối
  // chiếu dị ứng trong mô tả bệnh nhân. Hiện ngay trong tab Chẩn đoán, không ghi đi đâu.
  const handleSuggestTreatment = async () => {
    if (selectedDiagnosisIds.size === 0) return;
    const chosen = finalDiagnoses.filter((_, idx) => selectedDiagnosisIds.has(idx));
    const ranked = [...chosen].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    setIsPreparingHandoff(true);
    setTreatmentResult(null);
    try {
      const res = await fetch('/api/diagnosis-tree/treatment', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ diagnoses: ranked, exam_notes: examNotes,
                               patient_history: submittedPatientDesc || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Gợi ý điều trị thất bại.");
      }
      const treatment = await res.json();
      // Gán thẳng, kể cả khi null: "đã đối chiếu và không thấy gì" khác hẳn
      // "chưa đối chiếu".
      setAllergyCheck(treatment.allergy_check || null);
      setTreatmentResult({ ...treatment, diagnoses: ranked });
    } catch (err) {
      console.error("Error generating treatment suggestion:", err);
      showStatus('error', err.message);
    } finally {
      setIsPreparingHandoff(false);
    }
  };

  // Turns bare "[1]" citation markers from the LLM into a fake markdown link (#cite-1) so
  // react-markdown parses them as an <a>, which the custom `a` renderer below swaps for a citation badge.
  const preprocessCitations = (text) => (text || '').replace(/\[(\d+)\]/g, (_, num) => `[${num}](#cite-${num})`);

  // Nhãn hiển thị của một nguồn. Backend trả về doc_title (tên sách) và
  // citation ("Dược thư QGVN 2022, Q.1 — tr. 297"); các kết quả cũ trong lịch
  // sử tra cứu chỉ có doc_name nên vẫn phải có đường lui.
  const sourceTitle = (src) => src?.doc_title
    || documents.find(d => d.doc_name === src?.doc_name)?.doc_title
    || src?.doc_name || '';
  const sourceCitation = (src) =>
    src?.citation || (src?.kind === 'web' ? sourceTitle(src) || src.provider || 'Nguồn web'
      : `${sourceTitle(src)} — tr. ${src?.page_num ?? '?'}`);

  const isWebSource = (src) => src?.kind === 'web';

  /** Mở một nguồn: trang sách vào trình đọc, nguồn web sang tab mới. */
  const openSource = async (src, idx, logId = activeLogId) => {
    setSelectedSourceIndex(idx);
    if (logId && !isWebSource(src)) sendFeedback(logId, 'open', idx);
    if (isWebSource(src)) {
      if (src.url) window.open(src.url, '_blank', 'noopener,noreferrer');
      return;
    }
    await handleOpenPageReader(src.doc_name, src.page_num, src, src.quote || src.text || src.snippet);
    requestAnimationFrame(() => readerCardRef.current?.focus());
  };

  // "Hỏi về tài liệu này" — gắn tài liệu vào ô hỏi đáp; câu hỏi tiếp theo chỉ
  // tra trong tài liệu đó, ưu tiên các trang quanh trang đang đọc.
  const askAboutDocument = (src) => {
    if (!src?.doc_name) return;
    const doc = documents.find(d => d.doc_name === src.doc_name);
    setChatScope({
      doc_name: src.doc_name,
      doc_title: src.doc_title || doc?.doc_title || src.doc_name,
      page_num: src.page_num || null,
    });
    setDocumentPreview(null);
    goToChat();
    setTimeout(() => chatInputRef.current?.focus(), 0);
  };

  // Đoạn cần tô trên trang đang mở (nếu có).
  const quoteForActivePage = () =>
    readerQuote && activePage && readerQuote.doc_name === activePage.doc_name
      && readerQuote.page_num === activePage.page_num ? readerQuote.quote : null;

  const openMessageSource = (message, index) => {
    const source = message.sources?.[index];
    if (!source) return;
    setActiveSources(message.sources);
    setActiveLogId(message.logId || null);
    openSource(source, index, message.logId || null);
  };

  async function handleUploadPdf(file, attach) {
    const version = draftVersion.current;
    setUploadFromComposer(attach);
    const doc = await clinical.uploadDocument(file, settings.notifyEnabled);
    if (doc && attach && version === draftVersion.current) askAboutDocument(doc);
  }

  async function deleteChatDocument() {
    if (!deleteDocTarget || deletingDocument) return;
    const { doc_name } = deleteDocTarget;
    setDeletingDocument(true);
    try {
      await apiJson(`/api/documents/${encodeURIComponent(doc_name)}`, { method: 'DELETE' });
      setDeleteDocTarget(null);
      setChatScope(scope => scope?.doc_name === doc_name ? null : scope);
      setDocumentPreview(preview => preview?.doc_name === doc_name ? null : preview);
      setActivePage(page => page?.doc_name === doc_name ? null : page);
      await clinical.refreshDocuments();
      showStatus('success', 'Đã xóa tài liệu.');
    } catch (error) {
      setDeleteDocTarget(null);
      showStatus('error', error.message);
    } finally {
      setDeletingDocument(false);
    }
  }

  const citationBadgeClass = (num) => {
    if (num === 2) return 'citation-badge-2';
    if (num === 3) return 'citation-badge-3';
    if (num === 4) return 'citation-badge-4';
    return 'citation-badge-1';
  };

  const citationLinkComponent = (message) => ({ href, children, ...props }) => {
    if (href && href.startsWith('#cite-')) {
      const num = parseInt(href.replace('#cite-', ''), 10);
      const source = message.sources?.[num - 1];
      return (
        <button
          type="button"
          className={`citation-badge ${citationBadgeClass(num)}`}
          onClick={() => {
            if (source) openMessageSource(message, num - 1);
          }}
          title={source ? (source.citation || `${source.doc_name} - Trang ${source.page_num}`) : `Nguồn ${num}`}
        >
          {num}
        </button>
      );
    }
    return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
  };

  const renderSimpleMarkdown = (text) => (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
      {text || ''}
    </ReactMarkdown>
  );

  const renderMessageText = (message) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex, rehypeHighlight]}
      components={{ a: citationLinkComponent(message) }}
    >
      {preprocessCitations(message.text)}
    </ReactMarkdown>
  );

  return (
    <div className="fil-clinical-body">
      {activeTab === 'chat' && (
        <aside className="fil-chat-tools" data-open={historyOpen ?? 'auto'} aria-label="Phiên hỏi đáp và tài liệu">
          <div className="fil-chat-toolbar">
            <h2><MessageSquare size={21} aria-hidden="true" /> Phiên hỏi đáp</h2>
            <button type="button" className="fil-tool-action fil-mobile-history" aria-expanded={historyOpen === true}
              aria-controls="fil-chat-sidebar" onClick={toggleHistory}>
              Phiên hỏi đáp và tài liệu <ChevronDown size={15} aria-hidden="true" />
            </button>
          </div>
          <div id="fil-chat-sidebar">
            <button type="button" className="fil-button fil-new-chat" onClick={() => { handleNewChat(); chatInputRef.current?.focus(); }}>
              <SquarePen size={17} aria-hidden="true" /> Cuộc trò chuyện mới
            </button>
          <div id="fil-chat-history" className="fil-history-panel">
            {(() => {
              const visible = conversations
                .filter(c => !c.archived)
                .sort((x, y) => y.updatedAt - x.updatedAt);
              const pinned = visible.filter(c => c.pinned);
              const recents = visible.filter(c => !c.pinned);
              return (
                <>
                  {pinned.length > 0 && (
                    <div className="side-section">
                      <button
                        type="button"
                        className="side-section-label"
                        aria-expanded={pinnedOpen}
                        onClick={() => setPinnedOpen(v => !v)}
                      >
                        Đã ghim <ChevronRight size={12} className={pinnedOpen ? 'open' : ''} aria-hidden="true" />
                      </button>
                      {pinnedOpen && (
                        <AnimatePresence initial={false}>{pinned.map(renderConvItem)}</AnimatePresence>
                      )}
                    </div>
                  )}
                  <div className="side-section">
                    <button
                      type="button"
                      className="side-section-label"
                      aria-expanded={recentsOpen}
                      onClick={() => setRecentsOpen(v => !v)}
                    >
                      Gần đây <ChevronRight size={12} className={recentsOpen ? 'open' : ''} aria-hidden="true" />
                    </button>
                    {recentsOpen && (recents.length === 0 ? (
                      <div className="sidebar-history-empty">
                        Chưa có cuộc trò chuyện nào.
                      </div>
                    ) : (
                      <AnimatePresence initial={false}>{(showAllRecent ? recents : recents.slice(0, 4)).map(renderConvItem)}</AnimatePresence>
                    ))}
                    {recentsOpen && recents.length > 4 && (
                      <button type="button" className="fil-show-more" aria-expanded={showAllRecent} onClick={() => setShowAllRecent(value => !value)}>
                        {showAllRecent ? 'Thu gọn' : `Xem thêm (${recents.length - 4})`} <ChevronDown size={15} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
          <ChatDocuments clinical={clinical} readOnly={user?.read_only} pickerOpen={pickerOpen} setPickerOpen={setPickerOpen}
            onPreview={doc => handleOpenDocumentPreview(doc.doc_name, readerMinPage(doc.doc_name))}
            onAttach={askAboutDocument} onUpload={handleUploadPdf} onDownload={handleDownloadDocument}
            onDelete={setDeleteDocTarget} />
          </div>
        </aside>
      )}

      <Dialog.Root open={!!deleteDocTarget} onOpenChange={open => { if (!open && !deletingDocument) setDeleteDocTarget(null); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Title className="dialog-title">Xóa tài liệu?</Dialog.Title>
            <Dialog.Description className="dialog-description">
              {deleteDocTarget?.doc_title || deleteDocTarget?.doc_name} sẽ bị xóa khỏi kho tra cứu.
            </Dialog.Description>
            <div className="dialog-actions">
              <Dialog.Close asChild><button type="button" className="btn-dialog-secondary" disabled={deletingDocument}>Hủy</button></Dialog.Close>
              <button type="button" className="btn-dialog-danger" disabled={deletingDocument} onClick={deleteChatDocument}>Xóa tài liệu</button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Delete-conversation confirmation dialog */}
      <Dialog.Root open={!!deleteTargetId} onOpenChange={(open) => !open && setDeleteTargetId(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Title className="dialog-title">Xóa cuộc trò chuyện?</Dialog.Title>
            <Dialog.Description className="dialog-description">
              "{conversations.find(c => c.id === deleteTargetId)?.title}" sẽ bị xóa vĩnh viễn. Hành động này không thể hoàn tác.
            </Dialog.Description>
            <div className="dialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="btn-dialog-secondary">Hủy</button>
              </Dialog.Close>
              <button type="button" className="btn-dialog-danger" onClick={confirmDeleteConversation}>Xóa</button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Share-conversation dialog */}
      <Dialog.Root open={!!shareDialog} onOpenChange={(open) => !open && setShareDialog(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Title className="dialog-title">Chia sẻ cuộc trò chuyện</Dialog.Title>
            <Dialog.Description className="dialog-description">
              Bất kỳ ai có liên kết này đều có thể xem lại nội dung cuộc trò chuyện (chỉ đọc).
            </Dialog.Description>
            <div className="share-link-row">
              <input
                readOnly
                className="share-link-input"
                value={shareDialog?.url || ''}
                onFocus={(e) => e.target.select()}
              />
              <button
                type="button"
                className="btn-copy-link"
                onClick={() => {
                  navigator.clipboard.writeText(shareDialog.url);
                  showStatus('success', 'Đã sao chép liên kết.');
                }}
              >
                <Copy size={14} />
                Sao chép
              </button>
            </div>
            <div className="dialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="btn-dialog-secondary">Đóng</button>
              </Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Source preview for chat attachments */}
      <Dialog.Root open={!!documentPreview} onOpenChange={(open) => !open && setDocumentPreview(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="lightbox-content lightbox-content-wide">
            {documentPreview && (
              <>
                <div className="lightbox-header">
                  <div className="lightbox-header-left">
                    <FileText size={17} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                    <Dialog.Title className="lightbox-title">{sourceTitle(documentPreview)}</Dialog.Title>
                  </div>
                  <div className="lightbox-header-actions">
                    <button
                      type="button"
                      className="btn-ask-document"
                      onClick={() => askAboutDocument(documentPreview)}
                    >
                      <MessageSquare size={18} aria-hidden="true" />
                      Hỏi về tài liệu này
                    </button>
                    <button className="icon-btn-action" onClick={() => handleDownloadDocument(documentPreview.doc_name)} title="Tải xuống">
                      <Download size={16} />
                    </button>
                    <Dialog.Close asChild>
                      <button className="icon-btn-action" title="Đóng"><X size={16} /></button>
                    </Dialog.Close>
                  </div>
                </div>
                <Dialog.Description className="sr-only">
                  Trang gốc của tài liệu {sourceTitle(documentPreview)}
                </Dialog.Description>
                <div className="library-page-body">
                  <PageViewer
                    key={`${documentPreview.doc_name}-${documentPreview.page_num}`}
                    docName={documentPreview.doc_name}
                    pageNum={documentPreview.page_num}
                    alt={`${sourceTitle(documentPreview)} — trang ${documentPreview.page_num}`}
                  />
                </div>
                <Pagination
                  current={documentPreview.page_num}
                  total={documents.find(d => d.doc_name === documentPreview.doc_name)?.page_count || documentPreview.page_num}
                  onChange={(p) => handleOpenDocumentPreview(documentPreview.doc_name, p)}
                />
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="fil-clinical-content">
        {config && !config.has_api_key && !apiKey && (
          <div className="alert-banner warning-banner">
            <AlertCircle size={16} aria-hidden="true" />
            <span>Chưa cấu hình khóa AI: câu trả lời AI sẽ không hiển thị, chỉ hiện trang sách.</span>
          </div>
        )}

        {statusMsg.text && (
          <div className={`alert-banner status-${statusMsg.type}`}
            role={statusMsg.type === 'error' ? 'alert' : 'status'}>
            {statusMsg.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Page / Tab Content Area */}
        <div className="fil-clinical-workflow">
          {/* TAB 1: Chat Dashboard (Split View) */}
          {activeTab === 'chat' && (
            <div className="chat-dashboard-split">
              <div className="fil-qa-main">
                <h1 className="sr-only">Hỏi đáp y khoa</h1>
              <div className={`chat-panel ${messages.length === 0 ? 'is-empty' : ''}`}>
                <h2 className="sr-only">{activeConversation?.title || 'Đặt câu hỏi'}</h2>
                {!messages.length && <div className="fil-qa-empty">
                  <span className="fil-tile"><MessageSquare size={23} aria-hidden="true" /></span>
                  <h2>Bắt đầu một câu hỏi</h2>
                  <p>Chọn một gợi ý hoặc nhập câu hỏi của bạn bên dưới.</p>
                  <div className="fil-qa-prompts" aria-label="Câu hỏi gợi ý">
                    {CHAT_PROMPTS.map(([label, prompt], index) => (
                      <button type="button" key={label} onClick={() => {
                        setQuery(prompt);
                        chatInputRef.current?.focus();
                      }}>{index === 0 && <Sparkles size={15} aria-hidden="true" />}{label}</button>
                    ))}
                  </div>
                </div>}

                {/* Conversation Scroller */}
                <div className="chat-messages-container">
                  {messages.map((msg, index) => (
                    <div key={index} className={`message-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}>
                      <div className={`fil-message-avatar ${msg.role === 'assistant' ? 'fil-assistant-mark' : ''}`} aria-hidden="true">
                        {msg.role === 'assistant' ? <Activity size={19} /> : <UserRound size={19} />}
                      </div>
                      <div className="message-bubble">
                      {msg.attachment && (
                        <div className="msg-attachments">
                          <AttachmentCard
                            title={msg.attachment.doc_title}
                            onOpen={() => handleOpenDocumentPreview(msg.attachment.doc_name, msg.attachment.page_num || readerMinPage(msg.attachment.doc_name))}
                          />
                        </div>
                      )}
                        {msg.normalized && (
                          <p className="bubble-normalized">
                            Đã tra theo: <strong>{msg.normalized.text}</strong>
                          </p>
                        )}
                        {msg.understood && <QueryUnderstood understood={msg.understood} />}
                        {msg.coverage?.length > 0 && (
                          <CoverageChecklist
                            items={msg.coverage}
                            sources={msg.sources}
                            onOpen={openSource}
                            citationOf={sourceCitation}
                          />
                        )}
                        {msg.statusNote && (
                          <p className="bubble-status" role="status">
                            <Loader2 size={13} className="animate-spin" />
                            {msg.statusNote}
                          </p>
                        )}
                        <div className="bubble-text">
                          {msg.role === 'assistant'
                            ? renderMessageText(msg)
                            : <p className="markdown-paragraph">{msg.text}</p>
                          }
                          {msg.streaming && msg.text && <span className="stream-caret" aria-hidden="true" />}
                          {msg.streaming && !msg.text && !msg.errorMessage && !msg.statusNote && (
                            <div className="loading-dots" role="status" aria-label="Đang tra cứu y văn">
                              <span />
                              <span />
                              <span />
                            </div>
                          )}
                        </div>
                        {msg.role === 'assistant' && !msg.streaming && msg.verify && (
                          <NumberCheck verify={msg.verify} />
                        )}
                        {msg.errorMessage && (
                          // role="alert" để máy đọc màn hình đọc ngay, không chờ
                          // bác sĩ tự dò tới. Khối này nằm DƯỚI phần chữ và
                          // KHÔNG thay thế trích dẫn: hỏng mô hình thì các trang
                          // sách bên dưới vẫn là thứ dùng được.
                          <div
                            className={`bubble-alert ${msg.degraded ? 'bubble-alert-degraded' : ''}`}
                            role="alert"
                          >
                            <AlertCircle size={14} />
                            <div>
                              <p className="bubble-alert-text">{msg.errorMessage}</p>
                              {msg.degraded && (msg.sources || []).length > 0 && (
                                <p className="bubble-alert-hint">
                                  {msg.sources.length} trang sách ở bên dưới vẫn tra được bình thường.
                                </p>
                              )}
                              {msg.errorDetail && (
                                <p className="bubble-alert-detail">{msg.errorDetail}</p>
                              )}
                            </div>
                          </div>
                        )}
                        {msg.cancelled && (
                          <p className="bubble-status bubble-status-muted">Đã dừng theo yêu cầu.</p>
                        )}
                        {/* Không ra trang nào là lúc bác sĩ dễ hiểu nhầm nhất. */}
                        {msg.role === 'assistant' && !msg.streaming && (msg.sources || []).length === 0
                          && !msg.errorMessage && !msg.cancelled && indexCoverage().length > 0 && (
                          <div className="coverage-notice" role="note">
                            <BookOpen size={14} />
                            <div>
                              <p>Kho tài liệu hiện chỉ có các chuyên luận trong phạm vi:</p>
                              <ul>
                                {indexCoverage().map(d => (
                                  <li key={d.doc_name}>
                                    <strong>{d.doc_title || d.doc_name}</strong> — {d.coverage}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        )}
                        {msg.role === 'assistant' && !!msg.sources?.length && <div className="fil-message-sources">
                          <span>Nguồn</span>
                          {msg.sources.map((source, sourceIndex) => (
                            <button type="button" key={sourceIndex} onClick={() => openMessageSource(msg, sourceIndex)}>
                              <strong>[{sourceIndex + 1}]</strong> {sourceCitation(source)}
                            </button>
                          ))}
                        </div>}
                        <div className="bubble-footer">
                          {msg.reused && (
                            <span className="bubble-reused-tag" title="Kết quả lấy lại từ lịch sử tra cứu, không gọi lại AI">
                              <History size={11} />
                              Dùng lại kết quả đã lưu
                            </span>
                          )}
                          {msg.role === 'assistant' && (
                            <div className="bubble-actions">
                              <button onClick={() => copyToClipboard(msg.text)} title="Sao chép câu trả lời">
                                <Copy size={13} />
                              </button>
                              <button
                                title="Hữu ích"
                                aria-pressed={msg.rating === 'up'}
                                className={msg.rating === 'up' ? 'is-on' : ''}
                                disabled={!msg.logId}
                                onClick={() => rateMessage(activeConversationId, index, 'up')}
                              >
                                <ThumbsUp size={13} />
                              </button>
                              <button
                                title="Không hữu ích"
                                aria-pressed={msg.rating === 'down'}
                                className={msg.rating === 'down' ? 'is-on' : ''}
                                disabled={!msg.logId}
                                onClick={() => rateMessage(activeConversationId, index, 'down')}
                              >
                                <ThumbsDown size={13} />
                              </button>
                            </div>
                          )}
                          <span className="bubble-time">{msg.time}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>

                {/* Ô nhập kiểu ChatGPT: thẻ đính kèm ở trên, chữ ở giữa, nút ở dưới */}
                <form
                  onSubmit={(e) => { e.preventDefault(); handleSearch(); }}
                  className="chat-input-container composer"
                >
                  {uploadFromComposer && (clinical.upload?.pending || clinical.upload?.error) && (
                    <p className="fil-doc-status fil-composer-upload-status" role={clinical.upload.error ? 'alert' : 'status'}>
                      {clinical.upload.error || clinical.upload.stage || 'Đang nạp PDF…'}
                    </p>
                  )}
                  {chatScope && (
                    <div className="att-row">
                      <AttachmentCard
                        title={chatScope.doc_title}
                        onOpen={() => handleOpenDocumentPreview(chatScope.doc_name, chatScope.page_num || readerMinPage(chatScope.doc_name))}
                        onRemove={() => setChatScope(null)}
                      />
                    </div>
                  )}
                  <div className="fil-composer-line">
                  <button type="button" className="composer-icon-btn fil-composer-attach"
                    aria-label="Chọn tài liệu PDF" title="Chọn tài liệu PDF" onClick={() => setPickerOpen(true)}>
                    <Paperclip size={19} aria-hidden="true" />
                  </button>
                  <textarea
                    ref={chatInputRef}
                    className="input-textarea composer-textarea"
                    aria-label="Câu hỏi tra cứu y văn"
                    placeholder={isRecording === 'chat' ? 'Đang nghe… hãy nói câu hỏi của bạn' : 'Đặt câu hỏi về bệnh lý, thuốc, phác đồ…'}
                    rows={1}
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 208)}px`;
                    }}
                    onKeyDown={(e) => {
                      // isComposing: bộ gõ Telex/VNI đang ghép dấu thì Enter chưa phải là gửi.
                      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                        e.preventDefault();
                        handleSearch();
                      }
                    }}
                  />
                      {loading ? (
                        <button type="button" className="composer-send" aria-label="Dừng tra cứu" onClick={handleCancelSearch}>
                          <span className="composer-stop-square" aria-hidden="true" />
                        </button>
                      ) : (
                        <button type="submit" className="composer-send" aria-label="Gửi câu hỏi" disabled={!query.trim()}>
                          <Send size={22} strokeWidth={2.25} />
                        </button>
                      )}
                  </div>
                  <div className="composer-actions">
                    <div className="composer-actions-left">
                      <button type="button" className="fil-attach-label" onClick={() => setPickerOpen(true)}>
                        <Paperclip size={15} aria-hidden="true" /> Đính kèm PDF
                      </button>
                      {!webSearchOn && webSearchTools.length > 0 && (
                        <button
                          type="button"
                          className="composer-icon-btn"
                          aria-label="Tìm thêm trên web"
                          title="Tìm thêm trên web"
                          onClick={() => setWebSearchOn(true)}
                        >
                          <Globe size={19} aria-hidden="true" />
                        </button>
                      )}
                      {webSearchOn && webSearchTools.length > 0 && (
                        <span className="composer-mode-chip">
                          <Globe size={16} aria-hidden="true" /> Web
                          <button type="button" aria-label="Tắt tìm trên web" onClick={() => setWebSearchOn(false)}>
                            <X size={14} />
                          </button>
                        </span>
                      )}
                    </div>
                    <div className="composer-actions-right">
                      {settings.voiceInputEnabled && (
                        <button
                          type="button"
                          className={`composer-icon-btn ${isRecording === 'chat' ? 'recording' : ''}`}
                          onClick={() => handleToggleMic('chat', setQuery, () => handleSearch())}
                          aria-label={isRecording === 'chat' ? 'Dừng ghi âm' : 'Ghi âm giọng nói'}
                          title={!micSupported ? 'Trình duyệt không hỗ trợ ghi âm' : (isRecording === 'chat' ? 'Dừng ghi âm' : 'Ghi âm giọng nói')}
                        >
                          {isRecording === 'chat' ? <Square size={14} /> : <Mic size={20} />}
                        </button>
                      )}
                    </div>
                  </div>
                </form>

              </div>

              </div>
              <aside className={`reference-panel fil-qa-references ${activePage ? 'reader-open' : ''}`} aria-labelledby="fil-references-title">
                <div className="fil-reference-heading">
                  <Layers size={24} aria-hidden="true" />
                  <div><h2 id="fil-references-title">Đối chứng tài liệu</h2>
                    <p>Các đoạn trích liên quan để kiểm chứng và đọc tại nguồn.</p>
                  </div>
                </div>
                  {/* Reader Viewer Card */}
                  {activePage && (
                    <div className="document-reader-card" ref={readerCardRef} tabIndex={-1}>
                      <div className="card-header">
                        <h3 className="reader-doc-title" title={sourceCitation(activePage)}>
                          {sourceTitle(activePage)} — Trang {activePage.page_num}
                        </h3>
                        <div className="reader-header-actions">
                          <button
                            type="button"
                            className="btn-ask-document"
                            onClick={() => askAboutDocument(activePage)}
                          >
                            <MessageSquare size={18} aria-hidden="true" />
                            Hỏi về tài liệu này
                          </button>
                          <button
                            className="reader-action-btn"
                            onClick={() => setReaderShowText(v => !v)}
                            aria-pressed={readerShowText}
                          >
                            {readerShowText ? <ScanLine size={18} aria-hidden="true" /> : <FileText size={18} aria-hidden="true" />}
                            {readerShowText ? 'Xem trang gốc' : 'Xem dạng chữ'}
                          </button>
                          {activeLogId && (
                            <button
                              className="reader-action-btn"
                              onClick={reportWrongPage}
                              disabled={wrongPages.has(`${activeLogId}:${selectedSourceIndex}`)}
                              title="Trang này không nói về câu hỏi — ghi lại để cải thiện tra cứu"
                            >
                              <Flag size={18} aria-hidden="true" />
                              {wrongPages.has(`${activeLogId}:${selectedSourceIndex}`) ? 'Đã báo sai trang' : 'Báo sai trang'}
                            </button>
                          )}
                          <button className="reader-action-btn" onClick={() => setActivePage(null)} title="Đóng trang, quay lại danh sách nguồn">
                            <X size={18} aria-hidden="true" /> Đóng
                          </button>
                        </div>
                      </div>

                      {/* Phạm vi quyển sách, ngay cạnh tên nó. */}
                      {(documents.find(d => d.doc_name === activePage.doc_name)?.coverage) && (
                        <p className="reader-coverage">
                          Quyển này chứa chuyên luận trong phạm vi{' '}
                          <strong>{documents.find(d => d.doc_name === activePage.doc_name).coverage}</strong>.
                        </p>
                      )}

                      {/* Tìm chữ trong CẢ tài liệu */}
                      <div className="reader-search-bar">
                        <Search size={15} className="reader-search-icon" />
                        <input
                          type="search"
                          className="reader-search-input"
                          placeholder="Tìm chữ trong tài liệu này…"
                          value={readerQuery}
                          onChange={(e) => setReaderQuery(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleSearchInDoc(); }}
                        />
                        <button
                          type="button"
                          className="reader-search-go"
                          onClick={handleSearchInDoc}
                          disabled={readerSearching || !readerQuery.trim()}
                        >
                          {readerSearching ? <Loader2 size={14} className="animate-spin" /> : 'Tìm'}
                        </button>
                        {readerHighlight && (
                          <button
                            type="button"
                            className="reader-search-clear"
                            onClick={() => { setReaderHighlight(''); setReaderMatches(null); setReaderQuery(''); }}
                          >
                            Bỏ tô sáng
                          </button>
                        )}
                      </div>

                      {readerSearching && (
                        <p className="reader-search-status" role="status">
                          Đang dựng chỉ mục chữ cho tài liệu này. Lần tìm đầu tiên sau khi mở app
                          mất khoảng mươi giây; những lần sau gần như tức thì.
                        </p>
                      )}

                      {readerMatches !== null && !readerSearching && (
                        <div className="reader-matches">
                          <div className="reader-matches-head">
                            {readerMatches.length === 0
                              ? 'Không có trang nào chứa cụm này.'
                              : `${readerMatches.length} trang có chứa “${readerHighlight}”`}
                            {readerTruncated && ' (đã cắt bớt)'}
                          </div>
                          <ul className="reader-matches-list">
                            {readerMatches.map((m) => (
                              <li key={m.page_num}>
                                <button
                                  type="button"
                                  className={`reader-match ${m.page_num === activePage.page_num ? 'current' : ''}`}
                                  onClick={() => handleOpenPageReader(activePage.doc_name, m.page_num)}
                                >
                                  <span className="reader-match-page">tr. {m.page_num}</span>
                                  <span className="reader-match-snippet">{m.snippet}</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className={`reader-content-body ${readerShowText ? '' : 'is-page'}`}>
                        {readerShowText ? (
                          readerHighlight
                            ? renderHighlightedText(activePage.text, readerHighlight)
                            : renderSimpleMarkdown(activePage.text)
                        ) : (
                          <PageViewer
                            docName={activePage.doc_name}
                            pageNum={activePage.page_num}
                            quote={quoteForActivePage()}
                            alt={`Ảnh trang gốc ${sourceCitation(activePage)}`}
                          />
                        )}
                      </div>

                      <div className="reader-footer-pagination">
                        <button onClick={handlePrevPage} disabled={activePage.page_num <= readerMinPage(activePage.doc_name)}>
                          <ChevronLeft size={16} />
                        </button>
                        {/* Ô gõ số trang. Form để phím Enter hoạt động đúng nghĩa. */}
                        <form
                          className="reader-page-jump"
                          onSubmit={(e) => { e.preventDefault(); handleGoToPage(readerPageInput); }}
                        >
                          <label className="sr-only" htmlFor="reader-page-input">Nhảy tới trang</label>
                          <span className="pagination-text">Trang</span>
                          <input
                            id="reader-page-input"
                            type="number"
                            className="reader-page-input"
                            min={readerMinPage(activePage.doc_name)}
                            max={readerMaxPage(activePage.doc_name) || undefined}
                            placeholder={String(activePage.page_num)}
                            value={readerPageInput}
                            onChange={(e) => setReaderPageInput(e.target.value)}
                            onBlur={() => setReaderPageInput('')}
                          />
                          <span className="pagination-text">/ {readerMaxPage(activePage.doc_name) || '?'}</span>
                        </form>
                        <button onClick={handleNextPage} disabled={activePage.page_num >= readerMaxPage(activePage.doc_name)}>
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    </div>
                  )}
                <div className="fil-reference-list">
                  {!activeSources.length && <div className="fil-reference-empty">
                    <BookOpen size={24} aria-hidden="true" />
                    <p>{loading ? 'Đang tìm nguồn trích dẫn…' : 'Nguồn trích dẫn sẽ xuất hiện khi có kết quả tra cứu.'}</p>
                  </div>}
                  {activeSources.map((source, index) => {
                    const web = isWebSource(source);
                    const excerpt = source.quote || source.snippet || source.text || '';
                    return (
                      <article key={index} className="fil-reference-card" data-selected={!!activePage && selectedSourceIndex === index}>
                        <div className="fil-reference-badges">
                          <span>Nguồn {index + 1}</span><span>{web ? 'Nguồn web' : 'Trích dẫn tài liệu'}</span>
                        </div>
                        <div className="fil-reference-doc">
                          <span className="fil-pdf-icon">{web ? <Globe size={19} aria-hidden="true" /> : <FileText size={19} aria-hidden="true" />}</span>
                          <div><h3>{sourceTitle(source) || source.provider || 'Nguồn tham khảo'}</h3>
                            <p>{web ? [source.provider, source.published].filter(Boolean).join(' · ') : `Trang ${source.page_num}`}</p>
                          </div>
                        </div>
                        {source.name_suspect && <p className="doc-ocr-warning"><AlertCircle size={13} /> Tên thuốc ở trang này bị lỗi OCR, đối chiếu bản scan</p>}
                        {excerpt && <blockquote>{excerpt.length > 480 ? `${excerpt.slice(0, 480).trimEnd()}…` : excerpt}</blockquote>}
                        <button className="fil-reference-action" type="button" onClick={() => openSource(source, index)}>
                          {web ? <ExternalLink size={16} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
                          {web ? 'Mở nguồn web' : 'Xem trong tài liệu'}
                        </button>
                      </article>
                    );
                  })}
                </div>
              </aside>
            </div>
          )}

          {/* TAB 4: Hồ sơ bệnh nhân (Patient Profile) */}
          {activeTab === 'diagnosisTree' && (
            <DiagnosisTreeView
              centerTreeCanvas={centerTreeCanvas}
              collectSymptoms={collectSymptoms}
              examLoading={examLoading}
              examNotes={examNotes}
              examResult={examResult}
              finalDiagnoses={finalDiagnoses}
              finalLoading={finalLoading}
              handleFinalDiagnosis={handleFinalDiagnosis}
              handleGenerateTree={handleGenerateTree}
              handleSuggestExam={handleSuggestExam}
              handleToggleDiagnosisSelected={handleToggleDiagnosisSelected}
              handleTreeCanvasMouseDown={handleTreeCanvasMouseDown}
              handleSuggestTreatment={handleSuggestTreatment}
              isPanningTree={isPanningTree}
              isPreparingHandoff={isPreparingHandoff}
              nodeStatusMap={nodeStatusMap}
              patientDesc={patientDesc}
              renderDecisionTreeNode={renderDecisionTreeNode}
              selectedDiagnosisDetail={selectedDiagnosisDetail}
              selectedDiagnosisIds={selectedDiagnosisIds}
              treatmentResult={treatmentResult}
              allergyCheck={allergyCheck}
              setExamNotes={setExamNotes}
              setPatientDesc={setPatientDesc}
              setSelectedDiagnosisDetail={setSelectedDiagnosisDetail}
              treeCanvasRef={treeCanvasRef}
              treeLoading={treeLoading}
              treePanOffset={treePanOffset}
              treeRoot={treeRoot}
              treeWrapperRef={treeWrapperRef}
              zoomScale={zoomScale}
              zoomTreeByDelta={zoomTreeByDelta}
            />
          )}

        </div>

      </div>

    </div>
  );
}

// Read-only viewer for a conversation shared via the "Chia sẻ" action — fetched from
// GET /api/share/:id, no app chrome, no editing, just the transcript.
export function SharedConversationView({ shareId }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' });

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/share/${shareId}`)
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Không tìm thấy cuộc trò chuyện được chia sẻ này.');
        }
        return res.json();
      })
      .then((data) => { if (!cancelled) setState({ status: 'ready', data, error: '' }); })
      .catch((err) => { if (!cancelled) setState({ status: 'error', data: null, error: err.message }); });
    return () => { cancelled = true; };
  }, [shareId]);

  return (
    <article className="fil-wrap fil-clinical fil-shared">
      <div className="shared-view-body">
        {state.status === 'loading' && (
          <div className="shared-view-status">
            <Loader2 className="animate-spin" size={22} />
            <span>Đang tải cuộc trò chuyện...</span>
          </div>
        )}
        {state.status === 'error' && (
          <div className="shared-view-status">
            <AlertCircle size={22} />
            <span>{state.error}</span>
          </div>
        )}
        {state.status === 'ready' && (
          <div className="shared-view-content">
            <h1 className="shared-view-title">{state.data.title}</h1>
            <p className="shared-view-readonly-note">Cuộc trò chuyện được chia sẻ · chỉ đọc</p>
            <div className="shared-view-messages">
              {state.data.messages.map((msg, idx) => (
                <div key={idx} className={`message-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}>
                  {msg.role === 'assistant' && (
                    <div className="assistant-avatar"><Sparkles size={16} className="avatar-spark" /></div>
                  )}
                  <div className="message-bubble">
                    <div className="bubble-text">
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                          {msg.text || ''}
                        </ReactMarkdown>
                      ) : (
                        <p className="markdown-paragraph">{msg.text}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
