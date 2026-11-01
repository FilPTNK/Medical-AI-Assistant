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
import SettingsDialog from './components/SettingsDialog';
import AccountMenu from './components/AccountMenu';
import PageViewer from './components/PageViewer';
import AttachmentCard from './components/AttachmentCard';
import NumberCheck from './components/NumberCheck';
import QueryUnderstood from './components/QueryUnderstood';
import CoverageChecklist from './components/CoverageChecklist';
import EditProfileDialog from './components/EditProfileDialog';
import useSettings from './components/useSettings';
import useProfiles from './components/useProfiles';
import Pagination from './components/Pagination';
import LibraryView from './components/LibraryView';
import useAuth from './components/useAuth';
import LoginScreen from './components/LoginScreen';
import ClinicAdminDialog, { ChangePasswordDialog } from './components/ClinicAdmin';
import DiagnosisTreeView from './components/DiagnosisTreeView';
import { apiSend } from './lib/apiClient';
import {
  AlertCircle,
  ArrowUp,
  Ban,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Copy,
  Download,
  ExternalLink,
  Globe,
  FileText,
  History,
  Library,
  Loader2,
  MessageSquare,
  Mic,
  Moon,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Pill,
  Pin,
  PinOff,
  Plus,
  ScanLine,
  Search,
  Share2,
  Sparkles,
  Square,
  SquarePen,
  Stethoscope,
  Sun,
  ThumbsDown,
  Flag,
  ThumbsUp,
  Trash2,
  X,
} from 'lucide-react';

const uid = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`);

const MAX_PINNED_CONVERSATIONS = 3;

const DRUG_QUICK_SUGGESTIONS = [
  "Amoxicilin",
  "Thuốc hạ huyết áp",
  "PPI",
  "Insulin",
  "Thuốc chống đông",
  "Paracetamol",
  "Cephalosporin"
];

// Ba chức năng duy nhất của app. `match` gom các tab con: "Tra cứu thuốc" gồm cả
// tra thuốc lẫn kệ sách tài liệu gốc.
const MAIN_TABS = [
  { id: 'chat', label: 'Cuộc trò chuyện mới', Icon: SquarePen, match: ['chat'] },
  { id: 'diagnosisTree', label: 'Chẩn đoán', Icon: Stethoscope, match: ['diagnosisTree'] },
  { id: 'medicine', label: 'Tra cứu thuốc', Icon: Pill, match: ['medicine', 'library'] },
];

export default function App() {
  // Read-only "shared conversation" route: /?share=<id> (query-based so any static host works)
  const shareViewId = new URLSearchParams(window.location.search).get('share');

  // Navigation & Page state
  const [activeTab, setActiveTab] = useState('chat'); // Mở thẳng vào Hỏi đáp y khoa, không màn giới thiệu
  // Every persisted preference behind the settings dialog lives in this hook.
  const settings = useSettings();
  const { isDarkMode, libraryViewMode, setLibraryViewMode } = settings;
  // Phiên đăng nhập & phân quyền — quyết định thấy hồ sơ của ai, sửa được gì.
  const auth = useAuth();
  const { user: currentUser, permissions } = auth;
  // Doctor identity (name/username/avatar) is API-backed — see components/useProfiles.js
  const profiles = useProfiles();
  const doctorName = currentUser?.display_name || profiles.activeProfile?.display_name || 'BS. Hà Thanh Hùng';
  const [clinicAdminOpen, setClinicAdminOpen] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const toggleTheme = () => settings.setAppearance(isDarkMode ? 'light' : 'dark');

  // Gỡ màn hình khởi động nằm trong index.html. Nó phải sống cho tới khi biết
  // chắc sẽ hiện cái gì tiếp theo — màn đăng nhập hay giao diện chính. Gỡ sớm
  // hơn là bác sĩ lại nhìn thấy một nhịp trắng đúng như trước.
  useEffect(() => {
    if (auth.status !== 'loading') window.__bootDone?.();
  }, [auth.status]);

  // Mọi API hồ sơ đều trả 401 khi chưa có phiên, nên dữ liệu ban đầu được tải ở
  // đây thay vì lúc mount — nếu không, danh sách bệnh nhân và tài liệu sẽ rỗng
  // vĩnh viễn sau khi đăng nhập.
  useEffect(() => {
    if (auth.status !== 'ready') return;
    profiles.refresh();
    fetchDocuments();
  }, [auth.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [showSourcesPanel, setShowSourcesPanel] = useState(true);

  // Core Data State
  const [documents, setDocuments] = useState([]);
  const [documentsError, setDocumentsError] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // "Thư viện" tab — ChatGPT Library-style gallery state
  const [librarySearch, setLibrarySearch] = useState('');
  const [librarySortBy, setLibrarySortBy] = useState('newest'); // 'newest' | 'oldest' | 'name' | 'pages'
  const [deleteDocTarget, setDeleteDocTarget] = useState(null); // doc_name | null
  const [libraryPreview, setLibraryPreview] = useState(null); // { doc_name, page_num, text } | null
  // Đợt 6 — gộp tab "Đối chiếu" vào Thư viện: chọn nhiều thẻ rồi so sánh ngay
  // tại chỗ, thay vì phải nhảy sang một tab riêng để chọn lại từ đầu.
  const [librarySelectMode, setLibrarySelectMode] = useState(false);
  const [librarySelectedDocs, setLibrarySelectedDocs] = useState([]); // [doc_name]
  const [showComparePanel, setShowComparePanel] = useState(false);
  const compareViewRef = useRef(null);
  // Tiến độ các lượt nạp PDF đang chạy nền (bác sĩ tự tải lên), theo dõi qua SSE —
  // xem handleFileUpload và backend/generic_ingest.py.
  const [uploadJobs, setUploadJobs] = useState([]); // [{jobId, docName, fileName, stage, current, total, status, error}]
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

  // Lịch sử tra cứu (tái sử dụng kết quả cũ thay vì hỏi lại AI)
  // { doc_name: số đoạn đã tô sáng }
  const [highlightCounts, setHighlightCounts] = useState({});
  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('deepseek_api_key') || '');
  // "Tìm thêm trên web": danh sách công cụ máy chủ bật (rỗng = ẩn nút), và lựa
  // chọn của bác sĩ — nhớ theo trình duyệt, mặc định tắt.
  const [webSearchTools, setWebSearchTools] = useState([]);
  const [webSearchOn, setWebSearchOn] = useState(() => {
    try { return localStorage.getItem('web_search_on') === '1'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem('web_search_on', webSearchOn ? '1' : '0'); } catch { /* chế độ riêng tư */ }
  }, [webSearchOn]);
  const [bannerMessage, setBannerMessage] = useState('');
  const [backendHasKey, setBackendHasKey] = useState(false);

  // "Cài đặt" tab state — doctor profile (moved here from the header pill) + ChatGPT-style preference toggles
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editProfileOpen, setEditProfileOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState('general');

  const openSettings = (section) => {
    if (section) setSettingsSection(section);
    setSettingsOpen(true);
  };

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

  // "Thuốc" (medicine lookup & AI report) state
  const [drugQuery, setDrugQuery] = useState('');
  const [drugLoading, setDrugLoading] = useState(false);
  // null = chưa tra cứu gì — hiện trạng thái rỗng thay vì báo cáo mẫu.
  const [drugReport, setDrugReport] = useState(null);
  const [activeDrugTocId, setActiveDrugTocId] = useState('1');
  const [selectedFactCheckDoc, setSelectedFactCheckDoc] = useState(null);
  const [showAllResourcesDialog, setShowAllResourcesDialog] = useState(false);
  const [copiedDrugToast, setCopiedDrugToast] = useState(false);
  const [resourceSearch, setResourceSearch] = useState('');

  // Voice input (Web Speech API) — shared between the Chat and Thuốc search bars
  const [isRecording, setIsRecording] = useState(null); // null | 'chat' | 'medicine'
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

  // Ô "Tình trạng bệnh nhân trước đó" (không bắt buộc) — gửi kèm cả bốn bước
  // của cây chẩn đoán. App không lưu hồ sơ bệnh nhân; chữ này chỉ sống trong phiên.
  const [patientHistory, setPatientHistory] = useState('');
  // Nguyên văn khối tiền sử backend đã gửi ra DeepSeek, trả ngược về để hiện
  // cho bác sĩ.
  const [patientContextSent, setPatientContextSent] = useState(null);
  const [allergyCheck, setAllergyCheck] = useState(null);
  const [patientContextOpen, setPatientContextOpen] = useState(false);
  // Gợi ý điều trị cho các chẩn đoán bác sĩ đã chọn, hiện ngay trong tab Chẩn đoán.
  const [treatmentResult, setTreatmentResult] = useState(null);

  // Multi-conversation state (ChatGPT-style): each conversation is its own thread with
  // a title, message list, and pin flag. Conversations persist to localStorage.
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null); // null = draft "new chat", not yet in the list
  const [conversationsLoaded, setConversationsLoaded] = useState(false);
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

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  // Suggested queries for Vietnamese UI
  const [greeting] = useState(() => {
    const options = [
      'Hôm nay bác sĩ cần tra cứu gì?',
      'Tôi có thể giúp gì cho bác sĩ?',
      'Bác sĩ muốn hỏi điều gì?',
    ];
    return options[Math.floor(Math.random() * options.length)];
  });
  const [composerMenuOpen, setComposerMenuOpen] = useState(false);
  const [convSearchOpen, setConvSearchOpen] = useState(false);
  const [convSearch, setConvSearch] = useState('');
  const [pinnedOpen, setPinnedOpen] = useState(true);
  const [recentsOpen, setRecentsOpen] = useState(true);

  // The dark-mode class and accent variable are applied by useSettings().

  // Global shortcuts — these are the ones listed in Settings → Phím tắt.
  useEffect(() => {
    const onKeyDown = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      const key = e.key.toLowerCase();

      if (key === 'k') {
        e.preventDefault();
        setActiveTab('chat');
        // wait for the chat view to mount before focusing
        setTimeout(() => chatInputRef.current?.focus(), 0);
      } else if (key === 'o' && e.shiftKey) {
        e.preventDefault();
        handleNewChat();
      } else if (key === 'b') {
        e.preventDefault();
        setIsSidebarCollapsed(v => !v);
      } else if (key === '/') {
        e.preventDefault();
        openSettings('keyboard');
      } else if (key === ',') {
        e.preventDefault();
        openSettings('general');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Cuộc trò chuyện nằm trong localStorage nên đọc được ngay; tài liệu và bệnh
  // nhân phải chờ đăng nhập xong (xem effect theo auth.status ở trên).
  useEffect(() => {
    const saved = localStorage.getItem('med_conversations');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) setConversations(parsed);
      } catch (err) {
        console.error("Error parsing saved conversations:", err);
      }
    }
    setConversationsLoaded(true);

    // Check if backend already has DeepSeek API key configured
    fetch('/api/config')
      .then(res => res.json())
      .then(data => {
        if (data && data.has_api_key) {
          setBackendHasKey(true);
        }
        setWebSearchTools(data?.web_search_tools || []);
      })
      .catch(err => console.error("Error fetching config status:", err));
  }, []);

  // Refresh documents list when switching tabs to ensure freshness (handles backend startup lag)
  useEffect(() => {
    fetchDocuments();
  }, [activeTab]);

  // Đếm lại số đoạn đã tô sáng khi mở Thư viện và sau khi đóng trình đọc
  useEffect(() => {
    if (activeTab === 'library' && !libraryPreview) fetchHighlightCounts();
  }, [activeTab, libraryPreview]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync API warning banner
  useEffect(() => {
    if (!apiKey && !backendHasKey) {
      setBannerMessage("Chưa cấu hình khóa AI: câu trả lời AI sẽ không hiển thị, chỉ hiện trang sách.");
    } else {
      setBannerMessage("");
    }
  }, [apiKey, backendHasKey]);

  // Auto-scroll chat window when new messages arrive
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Persist conversations to localStorage (skip the very first render, before the saved list has loaded)
  useEffect(() => {
    if (!conversationsLoaded) return;
    localStorage.setItem('med_conversations', JSON.stringify(conversations));
  }, [conversations, conversationsLoaded]);

  // Focus the inline rename input when entering rename mode
  useEffect(() => {
    if (renamingConvId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingConvId]);

  const fetchDocuments = async () => {
    setDocumentsError('');
    try {
      const res = await fetch('/api/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data || []);
      } else {
        setDocumentsError('Không tải được thư viện. Vui lòng thử lại.');
      }
    } catch (err) {
      console.error("Error fetching documents:", err);
      setDocumentsError('Không kết nối được với thư viện. Vui lòng thử lại.');
    }
  };

  // Số đoạn đã tô sáng theo từng tài liệu, hiển thị trên thẻ ở Thư viện
  const fetchHighlightCounts = async () => {
    try {
      const res = await fetch('/api/highlights/counts');
      if (res.ok) setHighlightCounts(await res.json());
    } catch (err) {
      console.error("Error fetching highlight counts:", err);
    }
  };

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
    setChatScope(null);
    setActiveConversationId(null);
    setDraftWelcome([]);
    setActiveSources([]);
    setActiveLogId(null);
    setActivePage(null);
    setSelectedSourceIndex(0);
    setQuery('');
    setActiveTab('chat');
  };

  const handleSelectConversation = (id) => {
    if (renamingConvId === id) return; // don't switch away while editing the title
    setActiveConversationId(id);
    setActiveTab('chat');
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
          onClick={() => handleSelectConversation(conv.id)}
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
            <span className="conv-item-title" title={conv.title}>{conv.title}</span>
          )}

          {renamingConvId !== conv.id && (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  className="conv-item-menu-btn"
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
    if (!q.trim()) return;

    setActiveTab('chat'); // Redirect to chat view when running search

    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    // Tài liệu đính kèm thuộc về CÂU HỎI NÀY (như ChatGPT): gửi xong thì thẻ
    // trong ô nhập biến mất, còn tin nhắn đã gửi giữ thẻ để biết câu nào hỏi
    // riêng trong sách nào.
    const attachment = chatScope;
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
          setActiveLogId(null);
          if (sources.length > 0) {
            // Trình đọc trang chỉ mở được trang sách; nguồn web mở ở tab mới.
            const firstBook = sources.findIndex(s => !isWebSource(s));
            setActiveSources(sources);
            setSelectedSourceIndex(Math.max(firstBook, 0));
            setActivePage(firstBook >= 0 ? sources[firstBook] : null);
          } else {
            setActiveSources([]);
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
          if (data.log_id) {
            patchLastMessage(convId, m => ({ ...m, logId: data.log_id }));
            setActiveLogId(data.log_id);
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
  const handleDrugLookup = async (queryText) => {
    const q = (typeof queryText === 'string' ? queryText : drugQuery).trim();
    if (!q) return;

    setDrugLoading(true);
    if (typeof queryText === 'string') {
      setDrugQuery(queryText);
    }

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (apiKey) {
        headers['X-DeepSeek-Key'] = apiKey;
      }

      const res = await fetch('/api/drugs/report', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: q })
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const detail = errorData?.detail;
        let message = "Không thể tạo báo cáo tra cứu thuốc.";
        if (typeof detail === 'string' && detail.trim()) {
          message = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          message = detail.map(d => (typeof d === 'string' ? d : d?.msg)).filter(Boolean).join('; ') || message;
        } else if (detail && typeof detail === 'object' && detail.msg) {
          message = detail.msg;
        }
        throw new Error(message);
      }

      // Báo cáo về theo luồng SSE thay vì một cục JSON: nguồn trích dẫn đến
      // trước, rồi từng đoạn nội dung. Nhờ vậy chữ đầu tiên hiện sau khoảng
      // nửa giây thay vì phải chờ trọn ~19s như bản chặn trước đây.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let meta = {};
      let data = null;
      let streamError = null;

      const handleFrame = (frame) => {
        const lines = frame.split('\n');
        const evLine = lines.find(l => l.startsWith('event: '));
        const dataLine = lines.find(l => l.startsWith('data: '));
        if (!evLine || !dataLine) return;
        const ev = evLine.slice(7).trim();
        let payload;
        try {
          payload = JSON.parse(dataLine.slice(6));
        } catch {
          return;
        }

        if (ev === 'meta') {
          meta = payload;
          // Xoá báo cáo cũ ngay, nếu không nội dung cũ còn dính lại trên màn
          // hình trong lúc báo cáo mới đang chảy về.
          setDrugReport({
            drug_name: q,
            subtitle: 'Đang tổng hợp dữ liệu dược lý...',
            confidence_overall: 'Cao',
            quick_summary: [],
            sections: [],
            ...payload
          });
          setActiveDrugTocId('1');
        } else if (ev === 'update') {
          data = { ...payload, ...meta };
          setDrugReport(data);
          // Tắt skeleton ngay khi có chữ đầu tiên, nếu không người dùng vẫn
          // chỉ thấy ô chờ tải trong suốt cả quá trình stream.
          setDrugLoading(false);
        } else if (ev === 'error') {
          streamError = payload?.detail || 'Không thể tạo báo cáo tra cứu thuốc.';
        }
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split('\n\n');
        buf = frames.pop();
        frames.forEach(handleFrame);
        if (streamError) break;
      }
      if (buf.trim()) handleFrame(buf);

      if (streamError) throw new Error(streamError);
      showStatus('success', `Đã tạo báo cáo tra cứu thuốc "${data?.drug_name || q}".`);
    } catch (err) {
      console.error("Error generating drug report:", err);
      showStatus('error', err.message);
    } finally {
      setDrugLoading(false);
    }
  };

  const handleCopyDrugReport = () => {
    if (!drugReport) return;
    let text = `# BÁO CÁO Y KHOA: ${drugReport.drug_name || 'TRA CỨU THUỐC'}\n`;
    if (drugReport.subtitle) text += `*${drugReport.subtitle}*\n`;
    text += `\n`;

    if (drugReport.quick_summary && drugReport.quick_summary.length > 0) {
      text += `## TÓM TẮT NHANH:\n`;
      drugReport.quick_summary.forEach(qs => {
        text += `- ${qs.text}\n`;
      });
      text += `\n`;
    }

    if (drugReport.sections && drugReport.sections.length > 0) {
      drugReport.sections.forEach(sec => {
        text += `## ${sec.title}\n${sec.content}\n\n`;
      });
    }


    navigator.clipboard.writeText(text);
    setCopiedDrugToast(true);
    setTimeout(() => setCopiedDrugToast(false), 2500);
    showStatus('success', 'Đã sao chép toàn bộ báo cáo vào bộ nhớ tạm.');
  };

  const handleCitationClick = (citationId) => {
    if (!drugReport || !drugReport.sources) return;
    const cleanId = String(citationId).replace(/[^\d]/g, '');
    const foundDoc = drugReport.sources.find(s => String(s.id) === cleanId) || drugReport.sources[parseInt(cleanId, 10) - 1] || drugReport.sources[0];
    if (foundDoc) {
      setSelectedFactCheckDoc(foundDoc);
    }
  };

  const renderDrugSectionContent = (content) => {
    if (!content) return null;
    const parts = content.split(/(\[\d+\])/g);
    return (
      <div className="drug-sec-text">
        {parts.map((part, index) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (match) {
            const citeNum = match[1];
            return (
              <button
                key={index}
                type="button"
                className="drug-inline-citation"
                title={`Kiểm chứng nguồn [${citeNum}]`}
                onClick={() => handleCitationClick(citeNum)}
              >
                [{citeNum}]
              </button>
            );
          }
          return (
            <ReactMarkdown
              key={index}
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <span>{children}</span>
              }}
            >
              {part}
            </ReactMarkdown>
          );
        })}
      </div>
    );
  };

  // Đợt 6 — nạp PDF không còn chờ một request duy nhất tới lúc xong (có thể
  // mất nhiều phút với PDF scan dày, phải OCR): tải lên trả về ngay job_id,
  // rồi theo dõi tiến độ thật qua SSE và hiện một thẻ tiến độ trong lưới Thư
  // viện — xem backend/generic_ingest.py + /api/documents/ingest.
  const updateUploadJob = (jobId, patch) => {
    setUploadJobs(prev => prev.map(j => (j.jobId === jobId ? { ...j, ...patch } : j)));
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (fileInputRef.current) fileInputRef.current.value = '';

    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 64 * 1024 * 1024) {
      showStatus('error', 'Chỉ hỗ trợ PDF tối đa 64 MiB và 300 trang.');
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    let jobId, docName, visibility;
    try {
      const res = await fetch('/api/documents/ingest', { method: 'POST', body: formData });
      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || 'Tải lên tệp thất bại.');
      }
      ({ job_id: jobId, doc_name: docName, visibility } = await res.json());
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
      setUploading(false);
      return;
    } finally {
      setUploading(false);
    }

    setUploadJobs(prev => [
      ...prev,
      { jobId, docName, fileName: file.name, stage: 'Đang chờ xử lý...', current: 0, total: 0, status: 'queued' },
    ]);

    try {
      const res = await fetch(`/api/documents/ingest/${encodeURIComponent(jobId)}/events`);
      await readSseStream(res, (event, data) => {
        if (event === 'error') {
          updateUploadJob(jobId, { status: 'error', error: data?.message || 'Lỗi không rõ.' });
          return;
        }
        // event === 'progress': dữ liệu là job dict của backend/ingest_jobs.py
        updateUploadJob(jobId, {
          stage: data.stage, current: data.current, total: data.total,
          status: data.status, error: data.error, warnings: data.warnings || [],
        });
        if (data.status === 'done') {
          const scope = visibility === 'private' ? 'vào kho riêng của bạn' : 'vào thư viện chung của phòng khám';
          showStatus('success', `Đã nạp xong "${file.name}" (${data.total || '?'} trang) ${scope}.`);
          fetchDocuments();
          setTimeout(() => setUploadJobs(prev => prev.filter(j => j.jobId !== jobId)), 2000);
        } else if (data.status === 'error') {
          showStatus('error', `Nạp "${file.name}" thất bại: ${data.error || 'lỗi không rõ.'}`);
        }
      });
    } catch (err) {
      console.error(err);
      updateUploadJob(jobId, { status: 'error', error: err.message });
    }
  };

  const dismissUploadJob = (jobId) => setUploadJobs(prev => prev.filter(j => j.jobId !== jobId));

  const handleDeleteDoc = async (docName) => {
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
        if (libraryPreview && libraryPreview.doc_name === docName) {
          setLibraryPreview(null);
        }
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || "Không thể xóa tài liệu.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const confirmDeleteDocument = () => {
    if (!deleteDocTarget) return;
    handleDeleteDoc(deleteDocTarget);
    setDeleteDocTarget(null);
  };

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
  const handleOpenLibraryPreview = (docName, pageNum = 1) => {
    setLibraryPreview({ doc_name: docName, page_num: pageNum });
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
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}`);
      if (res.ok) {
        const data = await res.json();
        setActivePage(data);
        if (quoteToHighlight) setReaderQuote({ doc_name: docName, page_num: pageNum, quote: quoteToHighlight });
        if (quoteToHighlight) {
          // Neo được thì tô sáng, không neo được thì thôi — thà không tô gì còn
          // hơn tô nhầm chỗ.
          setReaderHighlight(bestAnchor(data.text || '', quoteToHighlight));
        }
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
      url.searchParams.set('doc', activePage.doc_name);
      url.searchParams.set('page', String(activePage.page_num));
    } else {
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
      setActiveTab('library');
      handleOpenPageReader(doc, page);
    }
  }, [documents]);

  const handleSaveApiKey = (value) => {
    setApiKey(value);
    localStorage.setItem('deepseek_api_key', value);
    showStatus('success', 'Đã cập nhật DeepSeek API Key thành công!');
  };

  // Settings → Kiểm soát dữ liệu → Xuất dữ liệu
  const handleExportData = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      doctor: {
        name: profiles.activeProfile?.display_name,
        username: profiles.activeProfile?.username,
        specialty: profiles.activeProfile?.specialty,
        email: profiles.activeProfile?.email,
      },
      custom_instructions: settings.customInstructions,
      conversations,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tro-ly-y-khoa-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showStatus('success', 'Đã xuất dữ liệu ra tệp JSON.');
  };

  // Settings → Kiểm soát dữ liệu → Lưu trữ tất cả (hides from the sidebar, keeps content)
  const handleArchiveAllConversations = () => {
    setConversations(prev => prev.map(c => ({ ...c, archived: true })));
    showStatus('success', 'Đã lưu trữ toàn bộ cuộc trò chuyện.');
  };

  // Settings → Tài khoản → Xóa toàn bộ dữ liệu cục bộ
  const handleResetLocalData = () => {
    if (!confirm('Xóa toàn bộ cài đặt và cuộc trò chuyện trên trình duyệt này? Hành động này không thể hoàn tác.')) return;
    localStorage.clear();
    window.location.reload();
  };

  const handleLogout = async () => {
    if (!confirm('Đăng xuất khỏi thiết bị này?')) return;
    setSettingsOpen(false);
    await auth.logout();
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    showStatus('success', 'Đã sao chép nội dung vào bộ nhớ tạm.');
  };

  const handleDeleteAllConversations = () => {
    if (!confirm("Xóa toàn bộ lịch sử trò chuyện? Hành động này không thể hoàn tác.")) return;
    setConversations([]);
    handleNewChat();
    showStatus('success', 'Đã xóa toàn bộ cuộc trò chuyện.');
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

  // Native (non-passive) wheel listener so we can preventDefault and zoom instead of scrolling the page
  useEffect(() => {
    const wrapper = treeWrapperRef.current;
    if (!wrapper) return;
    const handleWheel = (e) => {
      e.preventDefault();
      const rect = wrapper.getBoundingClientRect();
      zoomTreeAroundPoint(e.clientX - rect.left, e.clientY - rect.top, clampTreeZoom(zoomScale * Math.exp(-e.deltaY * 0.001)));
    };
    wrapper.addEventListener('wheel', handleWheel, { passive: false });
    return () => wrapper.removeEventListener('wheel', handleWheel);
  }, [zoomScale]);

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
    if (!patientDesc.trim()) return;
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
        body: JSON.stringify({ description: patientDesc, patient_history: patientHistory.trim() || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Tạo cây chẩn đoán thất bại.");
      }
      const data = await res.json();
      setDiagnosisTree(data);
      setPatientContextSent(data.patient_context || null);
      showStatus('success', patientHistory.trim()
        ? "Đã tạo cây chẩn đoán từ mô tả bệnh nhân và tình trạng trước đó."
        : "Đã tạo cây chẩn đoán từ mô tả bệnh nhân.");
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
                               patient_history: patientHistory.trim() || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Gợi ý khám & nội soi thất bại.");
      }
      const data = await res.json();
      setExamResult(data);
      if (data.patient_context) setPatientContextSent(data.patient_context);
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
                               patient_history: patientHistory.trim() || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Chẩn đoán cuối cùng thất bại.");
      }
      const data = await res.json();
      setFinalDiagnoses(data.diagnoses || []);
      if (data.patient_context) setPatientContextSent(data.patient_context);
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
  // chiếu dị ứng với ô tiền sử. Hiện ngay trong tab Chẩn đoán, không ghi đi đâu.
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
                               patient_history: patientHistory.trim() || null })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Gợi ý điều trị thất bại.");
      }
      const treatment = await res.json();
      if (treatment.patient_context) setPatientContextSent(treatment.patient_context);
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
    src?.citation || `${src?.doc_name || ''} — tr. ${src?.page_num ?? '?'}`;

  const isWebSource = (src) => src?.kind === 'web';

  /** Mở một nguồn: trang sách vào trình đọc, nguồn web sang tab mới. */
  const openSource = (src, idx) => {
    setSelectedSourceIndex(idx);
    if (activeLogId && !isWebSource(src)) sendFeedback(activeLogId, 'open', idx);
    if (isWebSource(src)) {
      if (src.url) window.open(src.url, '_blank', 'noopener,noreferrer');
      return;
    }
    handleOpenPageReader(src.doc_name, src.page_num, src, src.quote || src.text || src.snippet);
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
    setSelectedFactCheckDoc(null);
    setLibraryPreview(null);
    setActiveTab('chat');
    setTimeout(() => chatInputRef.current?.focus(), 0);
  };

  // Đoạn cần tô trên trang đang mở (nếu có).
  const quoteForActivePage = () =>
    readerQuote && activePage && readerQuote.doc_name === activePage.doc_name
      && readerQuote.page_num === activePage.page_num ? readerQuote.quote : null;

  const sourcePublisher = (src) => {
    if (isWebSource(src)) return [src.provider, src.published].filter(Boolean).join(' • ');
    const name = sourceTitle(src);
    if (name.includes('Dược thư')) return 'Bộ Y tế Việt Nam';
    if (name.includes('Hướng dẫn')) return 'Cục Quản lý Dược';
    if (name.includes('Hen')) return 'GINA Guidelines';
    return 'British National Formulary';
  };

  const citationBadgeClass = (num) => {
    if (num === 2) return 'citation-badge-2';
    if (num === 3) return 'citation-badge-3';
    if (num === 4) return 'citation-badge-4';
    return 'citation-badge-1';
  };

  const citationLinkComponent = (sources) => ({ href, children, ...props }) => {
    if (href && href.startsWith('#cite-')) {
      const num = parseInt(href.replace('#cite-', ''), 10);
      const source = sources?.[num - 1];
      return (
        <button
          type="button"
          className={`citation-badge ${citationBadgeClass(num)}`}
          onClick={() => {
            if (source) openSource(source, num - 1);
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

  const renderMessageText = (text, sources) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex, rehypeHighlight]}
      components={{ a: citationLinkComponent(sources) }}
    >
      {preprocessCitations(text)}
    </ReactMarkdown>
  );

  if (shareViewId) {
    return <SharedConversationView shareId={shareViewId} />;
  }

  // Cổng đăng nhập: mọi API hồ sơ bệnh nhân đều đòi phiên hợp lệ, nên không
  // render giao diện chính khi chưa đăng nhập.
  if (auth.status === 'loading') {
    return (
      <div className="app-boot">
        <Loader2 size={22} className="animate-spin" />
        <span>Đang khởi động Trợ lý Fil…</span>
      </div>
    );
  }

  if (auth.status !== 'ready') {
    return (
      <LoginScreen
        mode={auth.status}
        onLogin={auth.login}
        onSetup={auth.setup}
        onRetry={auth.recheck}
        serverAuth={auth.serverAuth}
        onGoogleLogin={auth.loginWithGoogle}
        onRegister={auth.startRegistration}
        onVerifyRegistration={auth.verifyRegistration}
        onResendCode={auth.resendRegistrationCode}
      />
    );
  }

  return (
    <div className="desktop-layout">
      {/* 1. Left Vertical Navigation Sidebar (ChatGPT-style expanded rail) */}
      <aside className={`left-sidebar${isSidebarCollapsed ? ' collapsed' : ''}`}>
        {/* Thanh bên kiểu ChatGPT: tên app + tìm/thu gọn, ba mục chính, rồi
            "Đã ghim" và "Gần đây". Số đo lấy từ chatgpt.com (28/10/2026):
            dòng 36px, chữ 14px, biểu tượng 20px, bo 8px. */}
        <div className="sidebar-brand">
          {!isSidebarCollapsed && <span className="sidebar-brand-name">Trợ lý Fil</span>}
          <div className="sidebar-brand-actions">
            {!isSidebarCollapsed && (
              <button
                type="button"
                className="sidebar-icon-btn"
                aria-label="Tìm đoạn chat"
                title="Tìm đoạn chat"
                aria-pressed={convSearchOpen}
                onClick={() => { setConvSearchOpen(v => !v); setConvSearch(''); }}
              >
                <Search size={20} />
              </button>
            )}
            <button
              type="button"
              className="sidebar-icon-btn"
              aria-label={isSidebarCollapsed ? 'Mở thanh bên' : 'Đóng thanh bên'}
              title={isSidebarCollapsed ? 'Mở thanh bên' : 'Đóng thanh bên'}
              onClick={() => setIsSidebarCollapsed(v => !v)}
            >
              {isSidebarCollapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
            </button>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Chức năng chính">
          {MAIN_TABS.map(({ id, label, Icon, match }) => {
            const isActive = id === 'chat'
              ? activeTab === 'chat' && !activeConversationId
              : match.includes(activeTab);
            return (
              <button
                key={id}
                type="button"
                className={`side-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => (id === 'chat' ? handleNewChat() : setActiveTab(id))}
                title={label}
              >
                <Icon size={20} aria-hidden="true" />
                {!isSidebarCollapsed && <span className="side-item-label">{label}</span>}
              </button>
            );
          })}
        </nav>

        {!isSidebarCollapsed && (
          <div className="sidebar-history-section">
            {convSearchOpen && (
              <input
                className="sidebar-search-input"
                type="search"
                autoFocus
                placeholder="Tìm đoạn chat…"
                aria-label="Tìm đoạn chat"
                value={convSearch}
                onChange={(e) => setConvSearch(e.target.value)}
              />
            )}
            {(() => {
              const needle = convSearch.trim().toLowerCase();
              const visible = conversations
                .filter(c => !c.archived)
                .filter(c => !needle || (c.title || '').toLowerCase().includes(needle))
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
                        {needle ? 'Không có đoạn chat nào khớp.' : 'Chưa có cuộc trò chuyện nào.'}
                      </div>
                    ) : (
                      <AnimatePresence initial={false}>{recents.map(renderConvItem)}</AnimatePresence>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        )}

        <div className="sidebar-footer">
          <ClinicAdminDialog
            open={clinicAdminOpen}
            onOpenChange={setClinicAdminOpen}
            currentUser={currentUser}
          />

          {/* Mở từ Cài đặt → Tài khoản, nên phải xếp lớp trên hộp thoại Cài đặt. */}
          <ChangePasswordDialog
            open={changePasswordOpen}
            onOpenChange={setChangePasswordOpen}
            onChangePassword={auth.changePassword}
            elevated
            hasPassword={currentUser?.has_password !== false}
          />

          <AccountMenu
            profiles={profiles.profiles}
            activeProfile={profiles.activeProfile}
            profileActions={profiles}
            onOpenSettings={() => openSettings('general')}
            onOpenSection={openSettings}
            onEditProfile={() => setEditProfileOpen(true)}
            onLogout={handleLogout}
            currentUser={currentUser}
            onOpenClinicAdmin={() => setClinicAdminOpen(true)}
          />
        </div>
      </aside>

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

      {/* Delete-document confirmation dialog (Thư viện) */}
      <Dialog.Root open={!!deleteDocTarget} onOpenChange={(open) => !open && setDeleteDocTarget(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Title className="dialog-title">Xóa tài liệu?</Dialog.Title>
            <Dialog.Description className="dialog-description">
              "{deleteDocTarget}" sẽ bị xóa khỏi chỉ mục và không thể tra cứu được nữa. Hành động này không thể hoàn tác.
            </Dialog.Description>
            <div className="dialog-actions">
              <Dialog.Close asChild>
                <button type="button" className="btn-dialog-secondary">Hủy</button>
              </Dialog.Close>
              <button type="button" className="btn-dialog-danger" onClick={confirmDeleteDocument}>Xóa</button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Document preview lightbox (Thư viện) — mirrors ChatGPT Library's inline file preview */}
      <Dialog.Root open={!!libraryPreview} onOpenChange={(open) => !open && setLibraryPreview(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="lightbox-content lightbox-content-wide">
            {libraryPreview && (
              <>
                <div className="lightbox-header">
                  <div className="lightbox-header-left">
                    <FileText size={17} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                    <Dialog.Title className="lightbox-title">{sourceTitle(libraryPreview)}</Dialog.Title>
                  </div>
                  <div className="lightbox-header-actions">
                    <button
                      type="button"
                      className="btn-ask-document"
                      onClick={() => askAboutDocument(libraryPreview)}
                    >
                      <MessageSquare size={18} aria-hidden="true" />
                      Hỏi về tài liệu này
                    </button>
                    <button className="icon-btn-action" onClick={() => handleDownloadDocument(libraryPreview.doc_name)} title="Tải xuống">
                      <Download size={16} />
                    </button>
                    <Dialog.Close asChild>
                      <button className="icon-btn-action" title="Đóng"><X size={16} /></button>
                    </Dialog.Close>
                  </div>
                </div>
                <Dialog.Description className="sr-only">
                  Trang gốc của tài liệu {sourceTitle(libraryPreview)}
                </Dialog.Description>
                <div className="library-page-body">
                  <PageViewer
                    key={`${libraryPreview.doc_name}-${libraryPreview.page_num}`}
                    docName={libraryPreview.doc_name}
                    pageNum={libraryPreview.page_num}
                    alt={`${sourceTitle(libraryPreview)} — trang ${libraryPreview.page_num}`}
                  />
                </div>
                <Pagination
                  current={libraryPreview.page_num}
                  total={documents.find(d => d.doc_name === libraryPreview.doc_name)?.page_count || libraryPreview.page_num}
                  onChange={(p) => handleOpenLibraryPreview(libraryPreview.doc_name, p)}
                />
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Fact-Check Reader Dialog (NotebookLM-style citation & page inspector) */}
      <Dialog.Root open={!!selectedFactCheckDoc} onOpenChange={(open) => !open && setSelectedFactCheckDoc(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="factcheck-lightbox-content">
            {selectedFactCheckDoc && (
              <>
                <div className="factcheck-header">
                  <div className="factcheck-header-left">
                    <div className="drug-pdf-icon-badge">
                      <FileText size={16} />
                      <span className="pdf-label">PDF</span>
                    </div>
                    <div>
                      <Dialog.Title className="factcheck-title">
                        {sourceTitle(selectedFactCheckDoc)}
                      </Dialog.Title>
                      <div className="factcheck-subtitle">
                        Kiểm chứng trích dẫn • {sourceCitation(selectedFactCheckDoc)}
                      </div>
                    </div>
                  </div>
                  <div className="factcheck-header-actions">
                    <button
                      className="icon-btn-action"
                      onClick={() => handleDownloadDocument(selectedFactCheckDoc.doc_name)}
                      title="Tải xuống PDF"
                    >
                      <Download size={16} />
                    </button>
                    <Dialog.Close asChild>
                      <button className="icon-btn-action" title="Đóng">
                        <X size={16} />
                      </button>
                    </Dialog.Close>
                  </div>
                </div>

                <div className="factcheck-body">
                  <div className="factcheck-highlight-box">
                    <div className="factcheck-highlight-label">
                      <Sparkles size={15} />
                      <span>Đoạn trích dẫn đối chiếu từ AI (Evidence Snippet):</span>
                    </div>
                    <div className="factcheck-highlight-text">
                      "{selectedFactCheckDoc.snippet || selectedFactCheckDoc.text || 'Thông tin trích xuất từ tài liệu y khoa chính thức.'}"
                    </div>
                  </div>

                  {selectedFactCheckDoc.doc_name && selectedFactCheckDoc.page_num ? (
                    <div className="factcheck-page">
                      <PageViewer
                        docName={selectedFactCheckDoc.doc_name}
                        pageNum={selectedFactCheckDoc.page_num}
                        quote={selectedFactCheckDoc.quote || selectedFactCheckDoc.text || selectedFactCheckDoc.snippet}
                        alt={`Ảnh trang gốc ${sourceCitation(selectedFactCheckDoc)}`}
                      />
                    </div>
                  ) : (
                    <div className="factcheck-full-text-body">
                      {renderSimpleMarkdown(selectedFactCheckDoc.text || selectedFactCheckDoc.snippet || '')}
                    </div>
                  )}
                </div>

                <div className="factcheck-footer">
                  <span className="factcheck-footer-note">
                    <CheckCircle2 size={15} className="text-accent" />
                    Kiểm tra nội dung và trang gốc trước khi sử dụng thông tin.
                  </span>
                  {selectedFactCheckDoc.doc_name && (
                    <button
                      type="button"
                      className="btn-ask-document"
                      onClick={() => askAboutDocument(selectedFactCheckDoc)}
                    >
                      <MessageSquare size={18} aria-hidden="true" />
                      Hỏi về tài liệu này
                    </button>
                  )}
                  <Dialog.Close asChild>
                    <button type="button" className="btn-dialog-secondary">
                      Đóng
                    </button>
                  </Dialog.Close>
                </div>
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* All Resources Dialog */}
      <Dialog.Root open={showAllResourcesDialog} onOpenChange={setShowAllResourcesDialog}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="all-resources-dialog-content">
            <div className="lightbox-header">
              <div className="lightbox-header-left">
                <BookOpen size={18} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                <Dialog.Title className="lightbox-title">
                  Tất cả tài liệu tham khảo ({(drugReport?.sources || []).length})
                </Dialog.Title>
              </div>
              <Dialog.Close asChild>
                <button className="icon-btn-action" title="Đóng"><X size={16} /></button>
              </Dialog.Close>
            </div>
            <div className="all-resources-body">
              <div className="all-resources-search-wrap">
                <Search size={16} />
                <input
                  type="text"
                  placeholder="Tìm tài liệu theo tên..."
                  value={resourceSearch}
                  onChange={(e) => setResourceSearch(e.target.value)}
                  className="all-resources-search-input"
                />
              </div>
              <div className="all-resources-grid">
                {(drugReport?.sources || [])
                  .filter(s => s.doc_name.toLowerCase().includes(resourceSearch.toLowerCase()))
                  .map((src, idx) => (
                    <div
                      key={idx}
                      className="all-resource-card"
                      onClick={() => {
                        setSelectedFactCheckDoc(src);
                        setShowAllResourcesDialog(false);
                      }}
                    >
                      <div className="all-res-top">
                        <div className="drug-pdf-icon-badge">
                          <FileText size={16} />
                          <span className="pdf-label">PDF</span>
                        </div>
                        <span className="all-res-page">{src.page_num}</span>
                      </div>
                      <h4 className="all-res-title" title={sourceCitation(src)}>{sourceTitle(src)}</h4>
                      <p className="all-res-snippet">{src.snippet || src.text}</p>
                      <div className="all-res-footer">
                        <span className="all-res-size">{src.file_size || 'PDF • 2.5 MB'}</span>
                        <span className="all-res-action">Đối chiếu <ChevronRight size={14} /></span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* 2. Main Content Workspace */}
      <div className="main-workspace">
        {/* Top Header Bar */}
        <header className="workspace-header">
          <div className="header-info">
            <div className="brand-title-row">
              <h1 className="header-brand-title">
                {activeTab === 'chat'
                  ? (conversations.find(c => c.id === activeConversationId)?.title || 'Trợ lý Fil')
                  : (MAIN_TABS.find(t => t.match.includes(activeTab)) || MAIN_TABS[0]).label}
              </h1>
            </div>
          </div>
          <div className="header-actions">
            <button
              className="btn-theme-toggle"
              onClick={toggleTheme}
              aria-label={isDarkMode ? "Chuyển sang nền sáng" : "Chuyển sang nền tối"}
              title={isDarkMode ? "Chuyển sang nền sáng" : "Chuyển sang nền tối"}
            >
              {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
              <span>{isDarkMode ? 'Nền sáng' : 'Nền tối'}</span>
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
          <div className={`alert-banner status-${statusMsg.type}`}
            role={statusMsg.type === 'error' ? 'alert' : 'status'}>
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
              <div className={`chat-panel ${messages.length === 0 ? 'is-empty' : ''}`}>
                {/* Conversation Scroller */}
                <div className="chat-messages-container">
                  {messages.map((msg, index) => (
                    <div key={index} className={`message-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}>
                      {msg.role === 'assistant' && (
                        <div className="assistant-avatar">
                          <Sparkles size={16} className="avatar-spark" />
                        </div>
                      )}
                      {msg.attachment && (
                        <div className="msg-attachments">
                          <AttachmentCard
                            title={msg.attachment.doc_title}
                            onOpen={() => handleOpenLibraryPreview(msg.attachment.doc_name, msg.attachment.page_num || 1)}
                          />
                        </div>
                      )}
                      <div className="message-bubble">
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
                            ? renderMessageText(msg.text, msg.sources)
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

                {messages.length === 0 && <h1 className="chat-greeting">{greeting}</h1>}

                {/* Ô nhập kiểu ChatGPT: thẻ đính kèm ở trên, chữ ở giữa, nút ở dưới */}
                <form
                  onSubmit={(e) => { e.preventDefault(); handleSearch(); }}
                  className="chat-input-container composer"
                >
                  {chatScope && (
                    <div className="att-row">
                      <AttachmentCard
                        title={chatScope.doc_title}
                        onOpen={() => handleOpenLibraryPreview(chatScope.doc_name, chatScope.page_num || 1)}
                        onRemove={() => setChatScope(null)}
                      />
                    </div>
                  )}
                  <textarea
                    ref={chatInputRef}
                    className="input-textarea composer-textarea"
                    aria-label="Câu hỏi tra cứu y văn"
                    placeholder={isRecording === 'chat' ? 'Đang nghe… hãy nói câu hỏi của bạn' : 'Hỏi bất kỳ điều gì'}
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
                  <div className="composer-actions">
                    <div className="composer-actions-left">
                      <div className="composer-menu-wrap">
                        <button
                          type="button"
                          className="composer-icon-btn"
                          aria-label="Thêm"
                          aria-haspopup="menu"
                          aria-expanded={composerMenuOpen}
                          title="Thêm tài liệu hoặc công cụ"
                          onClick={() => setComposerMenuOpen(v => !v)}
                        >
                          <Plus size={20} />
                        </button>
                        {composerMenuOpen && (
                          <div className="composer-menu" role="menu" onMouseLeave={() => setComposerMenuOpen(false)}>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => { setComposerMenuOpen(false); setActiveTab('library'); }}
                            >
                              <FileText size={18} /> Đính kèm tài liệu từ thư viện
                            </button>
                            {webSearchTools.length > 0 && (
                              <button
                                type="button"
                                role="menuitemcheckbox"
                                aria-checked={webSearchOn}
                                onClick={() => { setComposerMenuOpen(false); setWebSearchOn(v => !v); }}
                              >
                                <Globe size={18} /> Tìm thêm trên web
                                {webSearchOn && <Check size={16} className="composer-menu-check" />}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
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
                      {loading ? (
                        <button type="button" className="composer-send" aria-label="Dừng tra cứu" onClick={handleCancelSearch}>
                          <span className="composer-stop-square" aria-hidden="true" />
                        </button>
                      ) : (
                        <button type="submit" className="composer-send" aria-label="Gửi câu hỏi" disabled={!query.trim()}>
                          <ArrowUp size={22} strokeWidth={2.25} />
                        </button>
                      )}
                    </div>
                  </div>
                </form>

              </div>

              {/* Right Column: References & Reader */}
              {showSourcesPanel && (
                <div className={`reference-panel ${activePage ? 'reader-open' : ''}`}>
                  {/* Reference list (NotebookLM-style Sources rail) */}
                  <div className="citation-list-card">
                    <div className="card-header">
                      <div className="card-header-left">
                        <BookOpen size={18} className="header-icon-blue" />
                        <h2>Nguồn ({activeSources.length})</h2>
                      </div>
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
                              onClick={() => openSource(src, idx)}
                            >
                              <div className="item-row-left">
                                <span className={`item-square-badge ${badgeClass}`}>{idx + 1}</span>
                                <div className="item-details">
                                  {/* doc_name là ID kỹ thuật ("DTQGVN-2022-Q1"); bác sĩ cần
                                      tên sách thật để biết mình đang đối chiếu với nguồn nào. */}
                                  <h3 className="doc-title" title={src.citation || src.doc_name}>
                                    {src.doc_title || src.doc_name}
                                  </h3>
                                  <p className="doc-publisher">
                                    {sourcePublisher(src)}
                                  </p>
                                  {/* Tên thuốc của đoạn này do OCR đọc hỏng. Nội dung
                                      vẫn là dữ liệu thuốc thật nên trang vẫn được trả
                                      về, nhưng bác sĩ phải biết cái NHÃN không đáng
                                      tin trước khi đọc theo nó. Có cả chữ và biểu
                                      tượng, không chỉ màu, để không phụ thuộc màu sắc. */}
                                  {src.name_suspect && (
                                    <p className="doc-ocr-warning">
                                      <AlertCircle size={12} />
                                      Tên thuốc ở trang này bị lỗi OCR, đối chiếu bản scan
                                    </p>
                                  )}
                                </div>
                              </div>
                              <div className="item-row-right">
                                {isWebSource(src) ? (
                                  <span className="doc-page-no doc-web-link" title={src.url}>
                                    {src.domain || 'Web'} <ExternalLink size={12} />
                                  </span>
                                ) : (
                                  <>
                                    <span className="doc-page-no">Trang {src.page_num}</span>
                                    {isSelected ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                  </>
                                )}
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
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Thuốc (Drug Lookup & AI Clinical Monograph) */}
          {(activeTab === 'medicine' || activeTab === 'library') && (
            <div className="segmented-switch" role="tablist" aria-label="Tra cứu thuốc">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'medicine'}
                className={activeTab === 'medicine' ? 'active' : ''}
                onClick={() => setActiveTab('medicine')}
              >
                <Pill size={18} aria-hidden="true" /> Tra một thuốc
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'library'}
                className={activeTab === 'library' ? 'active' : ''}
                onClick={() => setActiveTab('library')}
              >
                <Library size={18} aria-hidden="true" /> Sách &amp; tài liệu gốc
              </button>
            </div>
          )}

          {activeTab === 'medicine' && (
            <div className="drug-lookup-view">
              {/* Top Title & Subtitle */}
              <div className="drug-hero-header">
                <h1 className="drug-hero-title">Tra cứu thuốc</h1>
              </div>

              {/* Search Box Form */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleDrugLookup();
                }}
                className="drug-search-card"
              >
                <div className="drug-search-input-wrap">
                  <div className="drug-search-icon-left">
                    <Search size={20} />
                  </div>
                  <div className="drug-search-fields">
                    <input
                      type="text"
                      className="drug-search-input"
                      aria-label="Tên thuốc hoặc nhu cầu tra cứu"
                      placeholder={isRecording === 'medicine' ? "Đang nghe giọng nói của bác sĩ..." : "Nhập tên thuốc hoặc chức năng của thuốc..."}
                      value={drugQuery}
                      onChange={(e) => setDrugQuery(e.target.value)}
                    />
                    <div className="drug-search-placeholder-sub">
                      Ví dụ: Paracetamol, thuốc hạ sốt cho trẻ, kháng sinh viêm phổi cộng đồng...
                    </div>
                  </div>
                  <div className="drug-search-actions-right">
                    {settings.voiceInputEnabled && (
                      <button
                        type="button"
                        className={`btn-drug-mic ${isRecording === 'medicine' ? 'recording' : ''}`}
                        onClick={() => handleToggleMic('medicine', setDrugQuery, () => handleDrugLookup())}
                        title={!micSupported ? "Trình duyệt không hỗ trợ ghi âm" : (isRecording === 'medicine' ? "Dừng ghi âm" : "Ghi âm giọng nói")}
                      >
                        {isRecording === 'medicine' ? <Square size={14} /> : <Mic size={18} />}
                      </button>
                    )}
                    {drugQuery && (
                      <button
                        type="button"
                        className="btn-drug-clear"
                        onClick={() => setDrugQuery('')}
                        title="Xóa tìm kiếm"
                      >
                        <Trash2 size={16} />
                        <span>Xóa</span>
                      </button>
                    )}
                    <button
                      type="submit"
                      className="btn-drug-submit"
                      disabled={drugLoading || !drugQuery.trim()}
                    >
                      {drugLoading ? (
                        <>
                          <Loader2 size={17} className="animate-spin" />
                          <span>Đang truy vấn...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={17} />
                          <span>Truy vấn</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </form>

              {/* Quick Search Chips */}
              <div className="drug-suggestions-row">
                <span className="drug-suggestions-label">Gợi ý tìm kiếm:</span>
                <div className="drug-suggestions-chips">
                  {DRUG_QUICK_SUGGESTIONS.map((item, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="drug-suggestion-chip"
                      onClick={() => {
                        setDrugQuery(item);
                        handleDrugLookup(item);
                      }}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>

              {/* Main Content Grid: Left Report & Right Resources/Takeaways */}
              {!drugReport ? (
                <div className="drug-empty-state">
                  <div className="drug-empty-state-icon"><Pill size={26} /></div>
                  <h4>Chưa có tra cứu nào</h4>
                  <p>Nhập tên thuốc hoặc chọn một gợi ý ở trên — AI sẽ tổng hợp thông tin từ Dược thư Quốc gia (Quyển 1 &amp; 2) và Thuốc Biệt Dược, kèm trích dẫn để đối chiếu.</p>
                </div>
              ) : (
              <div className="drug-main-grid">
                {/* LEFT COLUMN: Báo cáo AI */}
                <div className="drug-report-card">
                  <div className="drug-report-card-header">
                    <div className="drug-report-meta-left">
                      <h2 className="drug-report-title">Báo cáo AI</h2>
                    </div>
                    <div className="drug-report-actions-right">
                      <button
                        type="button"
                        className={`btn-drug-copy ${copiedDrugToast ? 'copied' : ''}`}
                        onClick={handleCopyDrugReport}
                        title="Sao chép báo cáo vào clipboard"
                      >
                        {copiedDrugToast ? <Check size={16} /> : <Copy size={16} />}
                        <span>{copiedDrugToast ? 'Đã sao chép' : 'Sao chép'}</span>
                      </button>
                    </div>
                  </div>

                  <div className="drug-report-inner-layout">
                    {/* Inner Left: Mục lục Table of Contents */}
                    <div className="drug-toc-rail">
                      <h3 className="drug-toc-heading">Mục lục</h3>
                      <nav className="drug-toc-list">
                        {(drugReport.sections || []).map((sec) => {
                          const isActive = activeDrugTocId === String(sec.id);
                          return (
                            <button
                              key={sec.id}
                              type="button"
                              className={`drug-toc-item ${isActive ? 'active' : ''}`}
                              onClick={() => {
                                setActiveDrugTocId(String(sec.id));
                                const el = document.getElementById(`drug-sec-${sec.id}`);
                                if (el) {
                                  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                }
                              }}
                            >
                              <span className="drug-toc-item-title">{sec.title}</span>
                            </button>
                          );
                        })}
                      </nav>
                    </div>

                    {/* Inner Right: Detailed Sections Stream */}
                    <div className="drug-sections-stream">
                      {drugLoading ? (
                        <div className="drug-report-loading-state">
                          <Loader2 size={36} className="animate-spin text-primary" />
                          <h4>Đang tổng hợp thông tin thuốc…</h4>
                        </div>
                      ) : (
                        (drugReport.sections || []).map((sec) => (
                          <div
                            key={sec.id}
                            id={`drug-sec-${sec.id}`}
                            className={`drug-section-block ${activeDrugTocId === String(sec.id) ? 'focused' : ''}`}
                            onMouseEnter={() => setActiveDrugTocId(String(sec.id))}
                          >
                            <div className="drug-section-header">
                              <h3 className="drug-section-title">{sec.title}</h3>
                            </div>
                            <div className="drug-section-content">
                              {renderDrugSectionContent(sec.content)}
                            </div>
                            <div className="drug-section-badge-row">
                              <span className="drug-confidence-pill">
                                <CheckCircle2 size={13} />
                                Mức AI tự đánh giá: {sec.confidence || drugReport.confidence_overall || 'Chưa rõ'}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                {/* RIGHT COLUMN: Resources & Quick Summary */}
                <div className="drug-sidebar-column">
                  {/* Card 1: Tài liệu nguồn (Resources) */}
                  <div className="drug-resources-card">
                    <div className="drug-resources-header">
                      <h3 className="drug-resources-title">Tài liệu nguồn</h3>
                    </div>

                    <div className="drug-resources-list">
                      {(drugReport.sources || []).slice(0, 5).map((src, idx) => (
                        <div
                          key={idx}
                          className="drug-resource-item"
                          onClick={() => setSelectedFactCheckDoc(src)}
                          title="Nhấp để xem trang đối chiếu y văn"
                        >
                          <div className="drug-resource-icon-wrap">
                            <div className="drug-pdf-icon-badge">
                              <FileText size={16} />
                              <span className="pdf-label">PDF</span>
                            </div>
                          </div>
                          <div className="drug-resource-info">
                            <h4 className="drug-resource-doc-name" title={sourceCitation(src)}>
                              {sourceTitle(src)}
                            </h4>
                            <span className="drug-resource-meta">{src.field_name || src.file_size || 'PDF'}</span>
                          </div>
                          <div className="drug-resource-page-badge">
                            {src.page_num || `Trang ${idx + 1}`}
                          </div>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      className="btn-view-all-resources"
                      onClick={() => setShowAllResourcesDialog(true)}
                    >
                      <span>Xem tất cả tài liệu ({(drugReport.sources || []).length})</span>
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {/* Card 2: Tóm tắt nhanh */}
                  <div className="drug-quick-summary-card">
                    <h3 className="drug-quick-summary-title">Tóm tắt nhanh</h3>
                    <div className="drug-quick-summary-list">
                      {(drugReport.quick_summary || []).length === 0 && (
                        <p className="drug-quick-summary-empty">Không có tóm tắt nhanh cho lượt tra cứu này.</p>
                      )}
                      {(drugReport.quick_summary || []).map((item, idx) => {
                        const itemType = item.type || item.status || (item.icon === 'alert' ? 'warning' : item.icon === 'ban' ? 'danger' : 'success');
                        let IconComp = CheckCircle2;
                        let colorClass = 'status-success';
                        if (itemType === 'warning') {
                          IconComp = AlertCircle;
                          colorClass = 'status-warning';
                        } else if (itemType === 'danger' || itemType === 'ban') {
                          IconComp = Ban;
                          colorClass = 'status-danger';
                        }

                        return (
                          <div key={idx} className={`drug-summary-item ${colorClass}`}>
                            <IconComp size={17} className="drug-summary-item-icon" />
                            <span className="drug-summary-item-text">{item.text}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                </div>
              </div>
              )}
            </div>
          )}

          {/* TAB 3: Thư viện + Đối chiếu */}
          {activeTab === 'library' && (
            <LibraryView
              documents={documents}
              documentsError={documentsError}
              fetchDocuments={fetchDocuments}
              librarySearch={librarySearch}
              setLibrarySearch={setLibrarySearch}
              librarySortBy={librarySortBy}
              setLibrarySortBy={setLibrarySortBy}
              libraryViewMode={libraryViewMode}
              setLibraryViewMode={setLibraryViewMode}
              librarySelectMode={librarySelectMode}
              setLibrarySelectMode={setLibrarySelectMode}
              librarySelectedDocs={librarySelectedDocs}
              setLibrarySelectedDocs={setLibrarySelectedDocs}
              showComparePanel={showComparePanel}
              setShowComparePanel={setShowComparePanel}
              compareViewRef={compareViewRef}
              fileInputRef={fileInputRef}
              uploadJobs={uploadJobs}
              uploading={uploading}
              handleFileUpload={handleFileUpload}
              dismissUploadJob={dismissUploadJob}
              highlightCounts={highlightCounts}
              handleOpenLibraryPreview={handleOpenLibraryPreview}
              handleDownloadDocument={handleDownloadDocument}
              setDeleteDocTarget={setDeleteDocTarget}
              apiKey={apiKey}
              showStatus={showStatus}
            />
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
              patientContextSent={patientContextSent}
              patientContextOpen={patientContextOpen}
              setPatientContextOpen={setPatientContextOpen}
              isPanningTree={isPanningTree}
              isPreparingHandoff={isPreparingHandoff}
              nodeStatusMap={nodeStatusMap}
              patientDesc={patientDesc}
              renderDecisionTreeNode={renderDecisionTreeNode}
              selectedDiagnosisDetail={selectedDiagnosisDetail}
              selectedDiagnosisIds={selectedDiagnosisIds}
              patientHistory={patientHistory}
              setPatientHistory={setPatientHistory}
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

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        section={settingsSection}
        onSectionChange={setSettingsSection}
        settings={settings}
        profile={currentUser || profiles.activeProfile}
        profileActions={profiles}
        actions={{
          onEditProfile: () => setEditProfileOpen(true),
          apiKey,
          backendHasKey,
          onSaveApiKey: handleSaveApiKey,
          micSupported,
          conversationCount: conversations.length,
          documentCount: documents.length,
          onDeleteAllConversations: handleDeleteAllConversations,
          onExportData: handleExportData,
          onArchiveAll: handleArchiveAllConversations,
          onResetLocalData: handleResetLocalData,
          onLogout: handleLogout,
          onChangePassword: () => setChangePasswordOpen(true),
          hasPassword: currentUser?.has_password !== false,
        }}
      />

      {/* Standalone "Chỉnh sửa hồ sơ" dialog, opened from the account menu */}
      <EditProfileDialog
        open={editProfileOpen}
        onOpenChange={setEditProfileOpen}
        profile={profiles.activeProfile}
        profileActions={profiles}
        onSaved={(updated) => {
          auth.absorbProfile(updated);
          showStatus('success', 'Đã cập nhật hồ sơ bác sĩ.');
        }}
      />
    </div>
  );
}

// Read-only viewer for a conversation shared via the "Chia sẻ" action — fetched from
// GET /api/share/:id, no app chrome, no editing, just the transcript.
function SharedConversationView({ shareId }) {
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
    <div className="shared-view">
      <header className="shared-view-header">
        <div className="shared-view-brand">
          <div className="brand-logo"><Pill size={17} className="logo-icon" /></div>
          <strong>Trợ lý Fil</strong>
        </div>
        <a className="btn-shared-open-app" href="/">Mở Trợ lý Fil</a>
      </header>

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
    </div>
  );
}
