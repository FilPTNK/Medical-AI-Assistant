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
  BookOpen,
  Users,
  GitBranch,
  Activity,
  Heart
} from 'lucide-react';

// Clinical Decision Trees Database
const diagnosisTrees = {
  asthma: {
    title: "Cơn hen phế quản cấp",
    description: "Xử trí cơn hen phế quản cấp ở người lớn và trẻ em lớn theo GINA",
    startNode: "q1",
    nodes: {
      q1: {
        type: "question",
        text: "Bệnh nhân có triệu chứng hen cấp tính (Khó thở nặng, khò khè, nói không thành câu, co kéo cơ hô hấp phụ)?",
        options: [
          { text: "Có triệu chứng", nextNode: "q2" },
          { text: "Không có", nextNode: "not_acute" }
        ]
      },
      not_acute: {
        type: "outcome",
        status: "normal",
        text: "Chưa ghi nhận cơn hen phế quản cấp tính. Theo dõi và hướng dẫn sử dụng thuốc xịt kiểm soát dự phòng định kỳ.",
        actions: [
          "Kiểm tra kỹ thuật hít của bệnh nhân.",
          "Xem xét điều chỉnh liều corticoid hít (ICS) nếu kiểm soát hen kém."
        ]
      },
      q2: {
        type: "question",
        text: "Bệnh nhân có dấu hiệu đe dọa tính mạng (Tím tái, lơ mơ, phổi câm - không tiếng thở, SpO2 < 90%)?",
        options: [
          { text: "Có dấu hiệu nguy kịch", nextNode: "critical" },
          { text: "Không nguy kịch", nextNode: "q3" }
        ]
      },
      critical: {
        type: "outcome",
        status: "danger",
        text: "CẤP CỨU NGUY KỊCH: Chuyển khoa hồi sức tích cực (ICU) ngay lập tức!",
        actions: [
          "Thở oxy dòng cao duy trì SpO2 93-95% (94-98% ở phụ nữ có thai).",
          "Xịt khí dung Salbutamol + Ipratropium liên tục hoặc mỗi 20 phút.",
          "Tiêm tĩnh mạch Methylprednisolone 40-80mg.",
          "Tiêm tĩnh mạch Magnesi Sulfat 2g truyền chậm.",
          "Chuẩn bị đặt nội khí quản nếu có dấu hiệu suy hô hấp tiến triển."
        ]
      },
      q3: {
        type: "question",
        text: "Bệnh nhân có cơn hen mức độ trung bình (Nói từng từ, tư thế ngồi thẳng, co kéo cơ hô hấp nhẹ, SpO2 90 - 95%)?",
        options: [
          { text: "Mức độ Trung bình", nextNode: "moderate" },
          { text: "Mức độ Nhẹ", nextNode: "mild" }
        ]
      },
      moderate: {
        type: "outcome",
        status: "warning",
        text: "Xử trí cơn hen cấp mức độ TRUNG BÌNH tại cơ sở y tế:",
        actions: [
          "Thở oxy qua cannula duy trì SpO2 93-95%.",
          "Salbutamol xịt 4-10 nhát qua buồng đệm mỗi 20 phút trong 1 giờ đầu, hoặc khí dung Salbutamol 2.5-5mg.",
          "Uống Prednisolone 1mg/kg (tối đa 50mg) hoặc tiêm Methylprednisolone.",
          "Đánh giá lại sau 1 giờ: Nếu cải thiện, tiếp tục theo dõi điều trị ngoại trú; nếu không cải thiện, chuyển cấp cứu."
        ]
      },
      mild: {
        type: "outcome",
        status: "success",
        text: "Xử trí cơn hen cấp mức độ NHẸ (Nói cả câu, không co kéo cơ hô hấp phụ, SpO2 > 95%):",
        actions: [
          "Xịt Salbutamol (SABA) 2-4 nhát qua buồng đệm. Đánh giá lại sau 1 giờ.",
          "Nếu cắt được cơn hen hoàn toàn: Hướng dẫn bệnh nhân tiếp tục xịt SABA khi cần, kết hợp điều chỉnh thuốc dự phòng (ICS) và tái khám sau 1-2 tuần.",
          "Giáo dục sức khỏe về các yếu tố kích ứng cần tránh."
        ]
      }
    }
  },
  chest_pain: {
    title: "Đau ngực cấp",
    description: "Tiếp cận chẩn đoán và xử trí đau ngực cấp nghi do hội chứng vành cấp",
    startNode: "q1",
    nodes: {
      q1: {
        type: "question",
        text: "Đau ngực sau xương ức điển hình: Cảm giác đè ép, thắt chặt, đè nặng, lan lên vai/hàm trái, kéo dài > 15 phút?",
        options: [
          { text: "Đau điển hình", nextNode: "q2" },
          { text: "Đau không điển hình", nextNode: "atypical_pain" }
        ]
      },
      atypical_pain: {
        type: "question",
        text: "Bệnh nhân có đau ngực kiểu màng phổi (đau tăng khi hít sâu, ho) hoặc đau khu trú tại một điểm khi ấn vào?",
        options: [
          { text: "Có đau màng phổi/thành ngực", nextNode: "non_cardiac" },
          { text: "Không rõ nguyên nhân", nextNode: "q3" }
        ]
      },
      non_cardiac: {
        type: "outcome",
        status: "normal",
        text: "Đau ngực ít nghĩ tới tim mạch. Xem xét các nguyên nhân do cơ xương khớp, viêm màng phổi, trào ngược dạ dày thực quản (GERD) hoặc lo âu.",
        actions: [
          "Chỉ định thuốc giảm đau NSAIDs/Paracetamol nếu do cơ xương.",
          "Điều trị thử bằng thuốc ức chế bơm proton (PPI) nếu nghi ngờ GERD.",
          "Chụp X-quang phổi nếu có triệu chứng hô hấp."
        ]
      },
      q2: {
        type: "question",
        text: "Kết quả điện tâm đồ (ECG): Có ST chênh lên tại ít nhất 2 chuyển đạo liên tiếp hoặc Block nhánh trái mới xuất hiện?",
        options: [
          { text: "ECG có ST chênh lên", nextNode: "stemi" },
          { text: "ECG không chênh lên", nextNode: "q3" }
        ]
      },
      stemi: {
        type: "outcome",
        status: "danger",
        text: "CẤP CỨU: Nhồi máu cơ tim cấp có ST chênh lên (STEMI)!",
        actions: [
          "Kích hoạt đội can thiệp mạch vành (Cathlab) để tái thông mạch vành thì đầu (PCI) trong vòng 120 phút từ khi chẩn đoán.",
          "Cho ngay Aspirin 300mg (nhai) + Clopidogrel 300-600mg (hoặc Ticagrelor 180mg) uống.",
          "Nitroglycerin xịt dưới lưỡi nếu huyết áp tâm thu > 90 mmHg.",
          "Giảm đau bằng Morphine tiêm tĩnh mạch nếu đau ngực nhiều.",
          "Truyền Heparin không phân đoạn hoặc tiêm Enoxaparin."
        ]
      },
      q3: {
        type: "question",
        text: "Kết quả xét nghiệm Men tim (Troponin T hoặc I siêu nhạy) tăng động học?",
        options: [
          { text: "Troponin tăng", nextNode: "nstemi" },
          { text: "Troponin bình thường", nextNode: "unstable_angina" }
        ]
      },
      nstemi: {
        type: "outcome",
        status: "danger",
        text: "Nhồi máu cơ tim không ST chênh lên (NSTEMI):",
        actions: [
          "Nhập viện Đơn vị Hồi sức tim mạch (CCU).",
          "Điều trị kháng tiểu cầu kép: Aspirin + Ticagrelor/Clopidogrel.",
          "Điều trị kháng đông: Fondaparinux hoặc Enoxaparin.",
          "Sử dụng thuốc chẹn Beta nếu không có chống chỉ định, statin liều cao.",
          "Phân tầng nguy cơ để chụp mạch vành can thiệp trong vòng 24 - 72 giờ."
        ]
      },
      unstable_angina: {
        type: "outcome",
        status: "warning",
        text: "Cơn đau thắt ngực không ổn định (Unstable Angina) hoặc Đau ngực chưa loại trừ:",
        actions: [
          "Lặp lại xét nghiệm Troponin lần 2 sau 3 giờ để theo dõi động học.",
          "Thực hiện siêu âm tim kiểm tra chức năng thất trái và vận động vùng.",
          "Nếu Troponin vẫn âm tính và bệnh nhân hết đau ngực, xem xét nghiệm pháp gắng sức hoặc chụp MSCT mạch vành trước khi cho ra viện."
        ]
      }
    }
  },
  diabetes: {
    title: "Đái tháo đường Typ 2",
    description: "Tiếp cận chẩn đoán và lựa chọn phác đồ điều trị ban đầu theo Bộ Y tế",
    startNode: "q1",
    nodes: {
      q1: {
        type: "question",
        text: "Đường huyết đói >= 126 mg/dL (7.0 mmol/L) HOẶC HbA1c >= 6.5% HOẶC đường huyết bất kỳ >= 200 mg/dL kèm triệu chứng kinh điển (ăn nhiều, uống nhiều, tiểu nhiều, sụt cân)?",
        options: [
          { text: "Đạt tiêu chuẩn chẩn đoán", nextNode: "q2" },
          { text: "Chưa đạt tiêu chuẩn", nextNode: "pre_diabetes" }
        ]
      },
      pre_diabetes: {
        type: "outcome",
        status: "success",
        text: "Tiền đái tháo đường (HbA1c 5.7 - 6.4% hoặc Đường huyết đói 100 - 125 mg/dL):",
        actions: [
          "Can thiệp tích cực lối sống: Giảm cân (5-7% trọng lượng cơ thể), tập thể dục >= 150 phút/tuần.",
          "Xem xét sử dụng Metformin nếu bệnh nhân có nguy cơ cao tiến triển (BMI >= 25, tiền sử ĐTĐ thai kỳ, hoặc HbA1c sát mức 6.5%).",
          "Tầm soát lại đường huyết và HbA1c định kỳ mỗi năm."
        ]
      },
      q2: {
        type: "question",
        text: "Lúc chẩn đoán: HbA1c >= 9.0% HOẶC đường huyết quá cao (> 300 mg/dL) kèm triệu chứng sụt cân nhiều, nhiễm toan ceton?",
        options: [
          { text: "Có triệu chứng nặng/HbA1c cao", nextNode: "insulin_start" },
          { text: "Không nặng", nextNode: "q3" }
        ]
      },
      insulin_start: {
        type: "outcome",
        status: "danger",
        text: "Chỉ định điều trị bằng INSULIN ngay lập tức!",
        actions: [
          "Bắt đầu điều trị bằng Insulin nền (Basal insulin) liều 0.1 - 0.2 UI/kg hoặc phối hợp Insulin 2 pha.",
          "Kết hợp điều chỉnh chế độ ăn uống nghiêm ngặt.",
          "Theo dõi đường huyết mao mạch trước các bữa ăn và trước khi đi ngủ để chỉnh liều.",
          "Khi đường huyết ổn định và độc tính glucose giảm, có thể xem xét chuyển sang thuốc uống."
        ]
      },
      q3: {
        type: "question",
        text: "Bệnh nhân có bệnh tim mạch do xơ vữa (tiền sử NMCT, đột quỵ), suy tim, hoặc bệnh thận mạn (GFR < 60)?",
        options: [
          { text: "Có bệnh đồng mắc", nextNode: "comorbid_pathway" },
          { text: "Không có bệnh đồng mắc", nextNode: "standard_pathway" }
        ]
      },
      comorbid_pathway: {
        type: "outcome",
        status: "warning",
        text: "Phác đồ ưu tiên thuốc có lợi ích tim mạch - thận chứng minh:",
        actions: [
          "Lựa chọn Metformin làm nền tảng phối hợp thuốc.",
          "Ưu tiên nhóm SGLT2i (ức chế kênh đồng vận natri-glucose 2) nếu bệnh nhân suy tim hoặc bệnh thận mạn (đặc biệt albumin niệu tăng).",
          "Ưu tiên GLP-1 RA (đồng vận thụ thể GLP-1) hoặc SGLT2i nếu có bệnh tim mạch do xơ vữa chiếm ưu thế.",
          "Kiểm soát sát sao HbA1c mục tiêu < 7.0%."
        ]
      },
      standard_pathway: {
        type: "outcome",
        status: "success",
        text: "Phác đồ điều trị chuẩn: Metformin đơn trị liệu + Thay đổi lối sống:",
        actions: [
          "Bắt đầu bằng Metformin 500mg - 1000mg/ngày uống cùng bữa ăn, tăng dần liều để giảm tác dụng phụ tiêu hóa (liều tối đa 2000mg/ngày).",
          "Đánh giá lại HbA1c sau 3 tháng:",
          "Nếu chưa đạt mục tiêu (< 7.0%), phối hợp thêm thuốc thứ hai: Sulfonylurea (SU), DPP-4i, SGLT2i hoặc Pioglitazone."
        ]
      }
    }
  }
};

export default function App() {
  // Navigation & Page state
  const [activeTab, setActiveTab] = useState('chat'); // 'chat', 'litSearch', 'patients', 'diagnosisTree', 'about', 'settings'
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

  // Dynamic state for patients
  const [patients, setPatients] = useState([]);

  // Form states for new patient
  const [newPatName, setNewPatName] = useState('');
  const [newPatAge, setNewPatAge] = useState('');
  const [newPatGender, setNewPatGender] = useState('Nam');
  const [newPatDiagnosis, setNewPatDiagnosis] = useState('');
  const [newPatNotes, setNewPatNotes] = useState('');

  // Literature Search Tab specific states
  const [litQuery, setLitQuery] = useState('');
  const [litResults, setLitResults] = useState([]);
  const [litLoading, setLitLoading] = useState(false);
  const [activeLitTab, setActiveLitTab] = useState('search'); // 'search' or 'manage'

  // Diagnosis Tree state
  const [selectedTreeKey, setSelectedTreeKey] = useState(null);
  const [currentTreeNodeId, setCurrentTreeNodeId] = useState(null);
  const [treeHistory, setTreeHistory] = useState([]);

  // Chat message history
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Xin chào! Tôi là Trợ lý Y khoa MedRAG. Hãy tải tài liệu y văn dạng PDF của bạn lên mục **Tra cứu y văn**, sau đó đặt câu hỏi tại đây để tôi hỗ trợ tìm kiếm và trả lời chuyên sâu.',
      time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
    }
  ]);

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  // Suggested queries for Vietnamese UI
  const suggestions = [
    "Dấu hiệu đe dọa tính mạng của cơn hen phế quản cấp là gì?",
    "Phác đồ xử trí ban đầu cho bệnh nhân nhồi máu cơ tim STEMI?",
    "Khi nào chỉ định insulin ngay cho bệnh nhân đái tháo đường typ 2?"
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

  // Load backend documents, patients, and search history
  useEffect(() => {
    fetchDocuments();
    fetchPatients();
    const savedHistory = localStorage.getItem('med_search_history');
    if (savedHistory) {
      setSearchHistory(JSON.parse(savedHistory));
    }
  }, []);

  // Sync API warning banner
  useEffect(() => {
    if (!apiKey) {
      setBannerMessage("Cảnh báo: Chưa cấu hình DeepSeek API Key. Hãy nhập key trong mục Cài đặt để sử dụng tính năng Chat AI phản hồi đầy đủ.");
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

  const fetchPatients = async () => {
    try {
      const res = await fetch('/api/patients');
      if (res.ok) {
        const data = await res.json();
        setPatients(data || []);
      }
    } catch (err) {
      console.error("Error fetching patients:", err);
    }
  };

  const handleAddPatient = async (e) => {
    e.preventDefault();
    if (!newPatName.trim() || !newPatAge.trim() || !newPatDiagnosis.trim()) return;

    try {
      const res = await fetch('/api/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newPatName,
          age: parseInt(newPatAge, 10),
          gender: newPatGender,
          diagnosis: newPatDiagnosis,
          notes: newPatNotes
        })
      });

      if (res.ok) {
        showStatus('success', `Đã thêm hồ sơ bệnh nhân "${newPatName}" thành công.`);
        setNewPatName('');
        setNewPatAge('');
        setNewPatGender('Nam');
        setNewPatDiagnosis('');
        setNewPatNotes('');
        fetchPatients();
      } else {
        const data = await res.json();
        throw new Error(data.detail || "Không thể thêm bệnh nhân.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const handleDeletePatient = async (id) => {
    if (!confirm("Bạn có chắc chắn muốn xóa hồ sơ bệnh nhân này?")) return;
    try {
      const res = await fetch(`/api/patients/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        showStatus('success', "Đã xóa hồ sơ bệnh nhân thành công.");
        fetchPatients();
      } else {
        throw new Error("Không thể xóa bệnh nhân.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const showStatus = (type, text) => {
    setStatusMsg({ type, text });
    setTimeout(() => {
      setStatusMsg({ type: '', text: '' });
    }, 5000);
  };

  // Chat search (uses LLM)
  const handleSearch = async (searchQuery) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setActiveTab('chat'); // Redirect to chat view when running search
    setShowHistoryPopover(false);

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

  // Raw Literature Search (Dense + Sparse + RRF + Cross-Encoder, NO LLM)
  const handleLiteratureSearch = async (e) => {
    e?.preventDefault();
    if (!litQuery.trim()) return;

    setLitLoading(true);
    try {
      const res = await fetch('/api/literature-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: litQuery })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Yêu cầu tìm kiếm y văn thất bại.");
      }

      const data = await res.json();
      setLitResults(data.sources || []);
      
      if (data.sources && data.sources.length > 0) {
        setActiveSources(data.sources);
        setSelectedSourceIndex(0);
        handleOpenPageReader(data.sources[0].doc_name, data.sources[0].page_num, data.sources[0]);
      } else {
        setActiveSources([]);
        setActivePage(null);
      }
    } catch (err) {
      console.error(err);
      showStatus('error', err.message);
    } finally {
      setLitLoading(false);
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

  // Interactive Diagnosis Tree controllers
  const startDiagnosisTree = (key) => {
    const tree = diagnosisTrees[key];
    setSelectedTreeKey(key);
    setCurrentTreeNodeId(tree.startNode);
    setTreeHistory([]);
  };

  const handleTreeOptionClick = (option) => {
    setTreeHistory(prev => [...prev, { nodeId: currentTreeNodeId, answerText: option.text }]);
    setCurrentTreeNodeId(option.nextNode);
  };

  const handleTreeBack = () => {
    if (treeHistory.length === 0) return;
    const prevStep = treeHistory[treeHistory.length - 1];
    setTreeHistory(prev => prev.slice(0, -1));
    setCurrentTreeNodeId(prevStep.nodeId);
  };

  const handleTreeReset = () => {
    if (!selectedTreeKey) return;
    setCurrentTreeNodeId(diagnosisTrees[selectedTreeKey].startNode);
    setTreeHistory([]);
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
            className={`nav-item ${activeTab === 'litSearch' ? 'active' : ''}`}
            onClick={() => setActiveTab('litSearch')}
            title="Tra cứu y văn"
          >
            <BookOpen size={22} />
            <span>Y văn</span>
          </button>

          <button 
            className={`nav-item ${activeTab === 'patients' ? 'active' : ''}`}
            onClick={() => setActiveTab('patients')}
            title="Bệnh nhân"
          >
            <Users size={22} />
            <span>Bệnh nhân</span>
          </button>

          <button 
            className={`nav-item ${activeTab === 'diagnosisTree' ? 'active' : ''}`}
            onClick={() => setActiveTab('diagnosisTree')}
            title="Sơ đồ chẩn đoán"
          >
            <GitBranch size={22} />
            <span>Chẩn đoán</span>
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
            <p className="brand-subtitle">Trợ lý y khoa số hóa - Tra cứu hướng dẫn lâm sàng và y văn thông minh</p>
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
                  <h2>Trò chuyện lâm sàng AI</h2>
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
                      placeholder="Đặt câu hỏi lâm sàng dựa trên y văn đã chỉ mục..."
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
                    <span>Nguồn: Đối chiếu sách hướng dẫn điều trị Bộ Y Tế & GINA/ESC</span>
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
                      <h2>Nguồn Trích Dẫn ({activeSources.length})</h2>
                    </div>
                  </div>
                  <div className="card-subtitle">
                    Nhấp vào nguồn để đọc trang đầy đủ bên dưới
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
                                  {src.doc_name.includes("Dược thư") ? "Bộ Y tế Việt Nam" : 
                                   src.doc_name.includes("Hướng dẫn") ? "Cục Quản lý Dược" : 
                                   src.doc_name.includes("Hen") ? "GINA Guidelines" : "British National Formulary"}
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
                        <button className="icon-btn-action" title="Mở rộng">
                          <ExternalLink size={16} />
                        </button>
                        <button className="icon-btn-action" onClick={() => setActivePage(null)} title="Đóng">
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
                        Trang {activePage.page_num} / {
                          documents.find(d => d.doc_name === activePage.doc_name)?.page_count || '?'
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

          {/* TAB 2: Literature Search (Tra cứu y văn) */}
          {activeTab === 'litSearch' && (
            <div className="chat-dashboard-split">
              {/* Left Column: Search & Library Controls */}
              <div className="chat-panel">
                <div className="panel-header" style={{ justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <BookOpen size={18} className="panel-header-icon" />
                    <h2>Tra cứu y văn</h2>
                  </div>
                  {/* Toggle Sub-tab for Search or Document Management */}
                  <div className="lit-tab-buttons" style={{ display: 'flex', gap: '6px', background: 'var(--border)', padding: '2px', borderRadius: '6px' }}>
                    <button 
                      className={`btn-history-toggle ${activeLitTab === 'search' ? 'active' : ''}`}
                      onClick={() => setActiveLitTab('search')}
                      style={{ padding: '4px 10px', fontSize: '12px', border: 'none', background: activeLitTab === 'search' ? 'var(--bg-card)' : 'transparent', color: 'var(--text-primary)' }}
                    >
                      Tìm kiếm
                    </button>
                    <button 
                      className={`btn-history-toggle ${activeLitTab === 'manage' ? 'active' : ''}`}
                      onClick={() => setActiveLitTab('manage')}
                      style={{ padding: '4px 10px', fontSize: '12px', border: 'none', background: activeLitTab === 'manage' ? 'var(--bg-card)' : 'transparent', color: 'var(--text-primary)' }}
                    >
                      Thư viện ({documents.length})
                    </button>
                  </div>
                </div>

                {activeLitTab === 'search' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 60px)', padding: '16px 0' }}>
                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px', marginTop: 0 }}>
                      Hệ thống tìm kiếm trực tiếp các đoạn văn bản tương đồng cao nhất từ các hướng dẫn điều trị y khoa. (Sử dụng Hybrid Search + RRF + Reranker cục bộ, KHÔNG sử dụng LLM).
                    </p>
                    
                    <form onSubmit={handleLiteratureSearch} className="chat-input-container" style={{ position: 'relative', border: '1px solid var(--border)', background: 'var(--bg-card)', padding: '8px', borderRadius: '8px', marginBottom: '20px' }}>
                      <div className="input-row" style={{ display: 'flex', gap: '8px' }}>
                        <input 
                          type="text"
                          className="settings-input"
                          style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', padding: '6px', color: 'var(--text-primary)' }}
                          placeholder="Nhập triệu chứng, thuốc hoặc phác đồ để truy xuất..."
                          value={litQuery}
                          onChange={(e) => setLitQuery(e.target.value)}
                        />
                        <button type="submit" className="btn-send" style={{ background: '#2563eb', color: 'white', border: 'none', borderRadius: '6px', padding: '8px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center' }} disabled={litLoading || !litQuery.trim()}>
                          {litLoading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                        </button>
                      </div>
                    </form>

                    {/* Results list */}
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {litLoading ? (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '40px' }}>
                          <Loader2 className="animate-spin text-blue-500" size={30} />
                          <span style={{ marginLeft: '10px' }}>Đang truy xuất & tái xếp hạng văn bản...</span>
                        </div>
                      ) : litResults.length === 0 ? (
                        <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '40px' }}>
                          Chưa có kết quả tìm kiếm nào. Nhập câu hỏi ở trên để bắt đầu.
                        </div>
                      ) : (
                        litResults.map((res, idx) => {
                          const isSelected = activePage && activePage.doc_name === res.doc_name && activePage.page_num === res.page_num;
                          return (
                            <div 
                              key={idx}
                              className={`library-doc-item ${isSelected ? 'selected' : ''}`}
                              onClick={() => handleOpenPageReader(res.doc_name, res.page_num, res)}
                              style={{ 
                                display: 'flex', 
                                flexDirection: 'column', 
                                gap: '8px', 
                                padding: '14px', 
                                border: isSelected ? '1px solid #2563eb' : '1px solid var(--border)',
                                background: isSelected ? 'rgba(37, 99, 235, 0.04)' : 'var(--bg-card)',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                transition: 'all 0.2s ease'
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <span className="badge-beta" style={{ background: '#2563eb', color: 'white', textTransform: 'none', padding: '2px 6px', borderRadius: '4px', fontSize: '11px' }}>
                                    #{idx + 1}
                                  </span>
                                  <h4 style={{ margin: 0, fontSize: '14px', fontWeight: '600' }} title={res.doc_name}>
                                    {res.doc_name}
                                  </h4>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                  <span style={{ fontSize: '12px', color: '#16a34a', fontWeight: 'bold' }}>
                                    {(res.score * 100).toFixed(1)}% khớp
                                  </span>
                                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Trang {res.page_num}
                                  </span>
                                </div>
                              </div>
                              <p style={{ fontSize: '13px', margin: 0, color: 'var(--text-primary)', lineHeight: '1.4', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                {res.text}
                              </p>
                              {res.child_text && res.child_text !== res.text && (
                                <p style={{ fontSize: '11.5px', margin: '4px 0 0 0', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                  * Đoạn từ khóa khớp: \"{res.child_text.substring(0, 100)}...\"
                                </p>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                ) : (
                  // Manage documents / upload view (merged here)
                  <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 60px)', padding: '16px 0', gap: '16px' }}>
                    <div className="upload-card" style={{ padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px dashed var(--border)' }}>
                      <h3>Tải lên Tài liệu PDF</h3>
                      <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                        Tải lên tài liệu hướng dẫn điều trị để phục vụ tra cứu RAG cục bộ. Hệ thống sẽ tự động tiền xử lý tiếng Việt, chia nhỏ chunk theo Parent-Child và Summary Indexing.
                      </p>
                      
                      <div 
                        className="upload-dropzone"
                        onClick={() => fileInputRef.current?.click()}
                        style={{ height: '120px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', border: '2px dashed var(--border)', borderRadius: '8px', cursor: 'pointer' }}
                      >
                        <Upload size={28} className="upload-cloud-icon" />
                        <p className="dropzone-text" style={{ fontSize: '13px', margin: '6px 0' }}>{uploading ? "Đang xử lý tải lên..." : "Kéo thả hoặc nhấp để chọn tệp PDF"}</p>
                        <span className="dropzone-sub" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Dưới 50MB</span>
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
                        <div className="upload-progress-row" style={{ display: 'flex', gap: '6px', marginTop: '10px', fontSize: '12px', color: '#2563eb', alignItems: 'center' }}>
                          <Loader2 className="animate-spin" size={14} />
                          <span>Đang tiền xử lý & tạo chỉ mục vector...</span>
                        </div>
                      )}
                    </div>

                    <div className="library-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                      <h3 style={{ margin: '0 0 10px 0' }}>Tài liệu đã chỉ mục ({documents.length})</h3>
                      <div className="library-document-list" style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {documents.length === 0 ? (
                          <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-secondary)', fontSize: '13px' }}>Chưa có tài liệu nào. Vui lòng tải lên PDF ở trên!</div>
                        ) : (
                          documents.map((doc, idx) => (
                            <div key={idx} className="library-doc-item" style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--bg-card)', alignItems: 'center' }}>
                              <div className="doc-item-details" style={{ display: 'flex', flexDirection: 'column', gap: '2px', maxWidth: '85%' }}>
                                <h4 style={{ margin: 0, fontSize: '13.5px', fontWeight: '600', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={doc.doc_name}>
                                  {doc.doc_name}
                                </h4>
                                <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
                                  {doc.page_count} trang • {doc.chunk_count} chunks
                                </span>
                              </div>
                              <button 
                                className="btn-delete-doc"
                                onClick={(e) => handleDeleteDoc(doc.doc_name, e)}
                                title="Xóa tài liệu khỏi hệ thống"
                                style={{ padding: '6px', border: 'none', background: 'transparent', color: '#dc2626', cursor: 'pointer', borderRadius: '4px' }}
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column: References & Reader Viewer */}
              <div className="reference-panel">
                {activePage ? (
                  <div className="document-reader-card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', padding: '14px' }}>
                      <h3 className="reader-doc-title" style={{ margin: 0, fontSize: '14px', maxWidth: '80%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {activePage.doc_name} - Trang {activePage.page_num}
                      </h3>
                      <div className="reader-header-actions" style={{ display: 'flex', gap: '6px' }}>
                        <button className="icon-btn-action" title="Mở cửa sổ mới"><ExternalLink size={15} /></button>
                        <button className="icon-btn-action" onClick={() => setActivePage(null)} title="Đóng"><X size={15} /></button>
                      </div>
                    </div>
                    <div className="reader-content-body" style={{ flex: 1, padding: '16px', overflowY: 'auto', fontSize: '13.5px', lineHeight: '1.6' }}>
                      {renderSimpleMarkdown(activePage.text)}
                    </div>
                    <div className="reader-footer-pagination" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', borderTop: '1px solid var(--border)' }}>
                      <button onClick={handlePrevPage} disabled={activePage.page_num <= 1} style={{ padding: '4px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--bg-card)', color: 'var(--text-primary)', cursor: 'pointer' }}>
                        <ChevronLeft size={15} />
                      </button>
                      <span className="pagination-text" style={{ fontSize: '12.5px' }}>
                        Trang {activePage.page_num} / {
                          documents.find(d => d.doc_name === activePage.doc_name)?.page_count || '?'
                        }
                      </span>
                      <button onClick={handleNextPage} style={{ padding: '4px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--bg-card)', color: 'var(--text-primary)', cursor: 'pointer' }}>
                        <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', height: '100%', justifyContent: 'center', alignItems: 'center', color: 'var(--text-secondary)', fontSize: '13px' }}>
                    Chọn một đoạn kết quả tìm kiếm để đọc trang tài liệu chi tiết.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: Bệnh nhân (Patients Index) */}
          {activeTab === 'patients' && (
            <div className="meds-tab-view animate-fade-in">
              <div className="view-header">
                <h2>Hồ sơ Bệnh nhân</h2>
                <p>Quản lý hồ sơ bệnh nhân lâm sàng và đề xuất phác đồ điều trị từ y khoa</p>
              </div>

              <div className="docs-grid-layout">
                {/* Add Patient Card */}
                <div className="upload-card">
                  <h3>Thêm bệnh nhân mới</h3>
                  <form onSubmit={handleAddPatient} className="settings-form">
                    <div className="settings-form-group">
                      <label>Họ và tên</label>
                      <input 
                        type="text" 
                        className="settings-input" 
                        required 
                        value={newPatName} 
                        onChange={(e) => setNewPatName(e.target.value)}
                        placeholder="Ví dụ: Nguyễn Văn A"
                      />
                    </div>
                    <div style={{ display: 'flex', gap: '12px' }}>
                      <div className="settings-form-group" style={{ flex: 1 }}>
                        <label>Tuổi</label>
                        <input 
                          type="number" 
                          className="settings-input" 
                          required 
                          value={newPatAge} 
                          onChange={(e) => setNewPatAge(e.target.value)}
                          placeholder="Tuổi"
                        />
                      </div>
                      <div className="settings-form-group" style={{ flex: 1 }}>
                        <label>Giới tính</label>
                        <select 
                          className="settings-input" 
                          required 
                          value={newPatGender} 
                          onChange={(e) => setNewPatGender(e.target.value)}
                          style={{ height: '40px', padding: '0 8px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-primary)' }}
                        >
                          <option value="Nam">Nam</option>
                          <option value="Nữ">Nữ</option>
                          <option value="Khác">Khác</option>
                        </select>
                      </div>
                    </div>
                    <div className="settings-form-group">
                      <label>Chẩn đoán bệnh lý</label>
                      <input 
                        type="text" 
                        className="settings-input" 
                        required 
                        value={newPatDiagnosis} 
                        onChange={(e) => setNewPatDiagnosis(e.target.value)}
                        placeholder="Ví dụ: Viêm dạ dày cấp"
                      />
                    </div>
                    <div className="settings-form-group">
                      <label>Triệu chứng / Tiền sử bệnh</label>
                      <textarea 
                        className="settings-input" 
                        rows={3}
                        value={newPatNotes} 
                        onChange={(e) => setNewPatNotes(e.target.value)}
                        placeholder="Ví dụ: Đau thượng vị nhiều sau ăn, sốt nhẹ..."
                      />
                    </div>
                    <button type="submit" className="btn-save-settings">Thêm Bệnh Nhân</button>
                  </form>
                </div>

                {/* Patient List Card */}
                <div className="library-card">
                  <div className="library-header-row">
                    <h3>Danh sách bệnh nhân ({patients.length})</h3>
                  </div>
                  
                  <div className="library-document-list">
                    {patients.length === 0 ? (
                      <div className="popover-empty">Chưa có hồ sơ bệnh nhân nào. Hãy thêm bệnh nhân mới!</div>
                    ) : (
                      patients.map((pat, idx) => (
                        <div key={idx} className="library-doc-item" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '8px', padding: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h4 style={{ margin: 0, fontSize: '15px' }} title={pat.name}>{pat.name}</h4>
                            <button 
                              className="btn-delete-doc"
                              onClick={() => handleDeletePatient(pat.id)}
                              title="Xóa bệnh nhân"
                              style={{ padding: '4px' }}
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            <span>{pat.age} tuổi • Giới tính: {pat.gender}</span>
                          </div>
                          <p style={{ fontSize: '13px', margin: '4px 0', color: 'var(--text-primary)' }}>
                            <strong>Chẩn đoán:</strong> {pat.diagnosis}
                          </p>
                          {pat.notes && (
                            <p style={{ fontSize: '12.5px', margin: 0, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                              * {pat.notes}
                            </p>
                          )}
                          <div style={{ marginTop: '8px' }}>
                            <button 
                              className="btn-suggestion-chip"
                              onClick={() => handleSearch(`Bệnh nhân ${pat.age} tuổi chẩn đoán ${pat.diagnosis}. Triệu chứng/tiền sử: ${pat.notes}. Hãy tra cứu y văn đã tải lên để gợi ý phác đồ điều trị phù hợp.`)}
                              style={{ width: '100%', textAlign: 'center', display: 'flex', justifyContent: 'center', margin: 0 }}
                            >
                              <Sparkles size={12} style={{ marginRight: '6px' }} /> Tra cứu phác đồ điều trị bằng AI RAG
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: Diagnosis Tree (Sơ đồ chẩn đoán tương tác) */}
          {activeTab === 'diagnosisTree' && (
            <div className="meds-tab-view animate-fade-in">
              <div className="view-header">
                <h2>Sơ đồ chẩn đoán lâm sàng tương tác</h2>
                <p>Hệ thống hỗ trợ chẩn đoán và xử trí nhanh theo phác đồ chuẩn y khoa.</p>
              </div>

              {!selectedTreeKey ? (
                // Tree Selection Screen
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginTop: '10px' }}>
                  {Object.entries(diagnosisTrees).map(([key, tree]) => (
                    <div 
                      key={key} 
                      className="library-doc-item" 
                      onClick={() => startDiagnosisTree(key)}
                      style={{ 
                        flexDirection: 'column', 
                        alignItems: 'flex-start', 
                        padding: '24px', 
                        cursor: 'pointer', 
                        transition: 'all 0.3s ease',
                        border: '1px solid var(--border)',
                        background: 'var(--bg-card)',
                        borderRadius: '12px',
                        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                        {key === 'asthma' && <Activity size={24} style={{ color: '#2563eb' }} />}
                        {key === 'chest_pain' && <Heart size={24} style={{ color: '#dc2626' }} />}
                        {key === 'diabetes' && <Pill size={24} style={{ color: '#16a34a' }} />}
                        <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold' }}>{tree.title}</h3>
                      </div>
                      <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', margin: '0 0 16px 0', lineHeight: '1.4' }}>
                        {tree.description}
                      </p>
                      <button 
                        className="btn-suggestion-chip" 
                        style={{ margin: 0, alignSelf: 'stretch', display: 'flex', justifyContent: 'center', background: 'rgba(37, 99, 235, 0.08)', color: '#2563eb', fontWeight: '600' }}
                      >
                        Bắt đầu chẩn đoán
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                // Interactive Flowchart Wizard View
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '24px', marginTop: '10px' }}>
                  
                  {/* Left Box: Flowchart Assessment Wizard */}
                  <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '12px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)', paddingBottom: '14px' }}>
                      <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold' }}>
                        {diagnosisTrees[selectedTreeKey].title}
                      </h3>
                      <button 
                        className="btn-clear-history"
                        onClick={() => setSelectedTreeKey(null)}
                        style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                      >
                        <X size={14} /> Chọn sơ đồ khác
                      </button>
                    </div>

                    {/* Step History Path */}
                    {treeHistory.length > 0 && (
                      <div style={{ background: 'var(--border)', padding: '12px 16px', borderRadius: '8px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                        <span style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)' }}>Đã đánh giá:</span>
                        {treeHistory.map((step, idx) => {
                          const node = diagnosisTrees[selectedTreeKey].nodes[step.nodeId];
                          return (
                            <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', background: 'var(--bg-card)', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border)' }}>
                              <span style={{ color: 'var(--text-secondary)' }}>{idx + 1}. {node.text.substring(0, 30)}...</span>
                              <span style={{ color: '#2563eb', fontWeight: 'bold' }}>({step.answerText})</span>
                              {idx < treeHistory.length - 1 && <span style={{ color: 'var(--text-secondary)' }}>→</span>}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Active Wizard Content */}
                    {(() => {
                      const tree = diagnosisTrees[selectedTreeKey];
                      const currentNode = tree.nodes[currentTreeNodeId];
                      if (!currentNode) return null;

                      if (currentNode.type === "question") {
                        return (
                          <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '10px 0' }}>
                            <div style={{ display: 'flex', gap: '12px' }}>
                              <div style={{ background: 'rgba(37, 99, 235, 0.08)', color: '#2563eb', width: '36px', height: '36px', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', fontWeight: 'bold', flexShrink: 0 }}>
                                ?
                              </div>
                              <h4 style={{ margin: 0, fontSize: '16px', fontWeight: '600', lineHeight: '1.5' }}>
                                {currentNode.text}
                              </h4>
                            </div>
                            
                            <div style={{ display: 'flex', gap: '12px', marginLeft: '48px', flexWrap: 'wrap' }}>
                              {currentNode.options.map((opt, idx) => (
                                <button 
                                  key={idx}
                                  className="btn-save-settings"
                                  onClick={() => handleTreeOptionClick(opt)}
                                  style={{ 
                                    padding: '10px 24px', 
                                    background: opt.text.includes("Không") ? 'transparent' : '#2563eb', 
                                    color: opt.text.includes("Không") ? 'var(--text-primary)' : 'white',
                                    border: opt.text.includes("Không") ? '1px solid var(--border)' : 'none',
                                    borderRadius: '8px',
                                    cursor: 'pointer',
                                    fontWeight: 'bold',
                                    transition: 'all 0.2s ease'
                                  }}
                                >
                                  {opt.text}
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      } else {
                        // Outcome / Final recommendation card
                        let cardColor = '#2563eb'; // normal/success
                        let bgAlpha = 'rgba(37, 99, 235, 0.04)';
                        if (currentNode.status === 'danger') {
                          cardColor = '#dc2626';
                          bgAlpha = 'rgba(220, 38, 38, 0.04)';
                        } else if (currentNode.status === 'warning') {
                          cardColor = '#d97706';
                          bgAlpha = 'rgba(217, 119, 6, 0.04)';
                        } else if (currentNode.status === 'success') {
                          cardColor = '#16a34a';
                          bgAlpha = 'rgba(22, 163, 74, 0.04)';
                        }

                        return (
                          <div 
                            className="animate-fade-in"
                            style={{ 
                              display: 'flex', 
                              flexDirection: 'column', 
                              gap: '18px', 
                              border: `1.5px solid ${cardColor}`, 
                              background: bgAlpha, 
                              borderRadius: '8px', 
                              padding: '20px' 
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {currentNode.status === 'danger' && <AlertCircle size={20} style={{ color: cardColor }} />}
                              {currentNode.status === 'warning' && <AlertCircle size={20} style={{ color: cardColor }} />}
                              {currentNode.status === 'success' && <CheckCircle2 size={20} style={{ color: cardColor }} />}
                              <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 'bold', color: cardColor }}>
                                {currentNode.text}
                              </h4>
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              <h5 style={{ margin: '0 0 4px 0', fontSize: '13.5px', fontWeight: '600' }}>Các bước xử trí lâm sàng chỉ định:</h5>
                              <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {currentNode.actions.map((act, idx) => (
                                  <li key={idx} style={{ fontSize: '13px', lineHeight: '1.4', color: 'var(--text-primary)' }}>
                                    {act}
                                  </li>
                                ))}
                              </ul>
                            </div>

                            <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
                              <button 
                                className="btn-save-settings" 
                                onClick={handleTreeReset}
                                style={{ background: cardColor, color: 'white', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer' }}
                              >
                                Đánh giá lại từ đầu
                              </button>
                              <button 
                                className="btn-suggestion-chip"
                                onClick={() => {
                                  // Auto navigate to Literature search with query
                                  const baseQuery = diagnosisTrees[selectedTreeKey].title;
                                  setActiveTab('litSearch');
                                  setLitQuery(`Phác đồ xử trí ${baseQuery}`);
                                  // Run search
                                  setTimeout(() => {
                                    handleLiteratureSearch();
                                  }, 100);
                                }}
                                style={{ margin: 0, border: '1px solid var(--border)', background: 'var(--bg-card)' }}
                              >
                                Tra cứu thêm y văn
                              </button>
                            </div>
                          </div>
                        );
                      }
                    })()}

                    {/* Back / reset toolbar */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '16px', marginTop: 'auto' }}>
                      <button 
                        className="btn-history-toggle"
                        onClick={handleTreeBack}
                        disabled={treeHistory.length === 0}
                        style={{ display: 'flex', alignItems: 'center', gap: '4px', opacity: treeHistory.length === 0 ? 0.5 : 1 }}
                      >
                        <ChevronLeft size={14} /> Quay lại bước trước
                      </button>
                      <button 
                        className="btn-clear-history"
                        onClick={handleTreeReset}
                        disabled={treeHistory.length === 0}
                        style={{ opacity: treeHistory.length === 0 ? 0.5 : 1 }}
                      >
                        Bắt đầu lại
                      </button>
                    </div>
                  </div>

                  {/* Right Box: Guidelines Info Card */}
                  <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    <h3 style={{ margin: '0 0 10px 0', fontSize: '15px', fontWeight: 'bold' }}>Thông tin tham chiếu</h3>
                    <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                      <p style={{ marginTop: 0 }}>
                        Các sơ đồ được xây dựng dựa trên hướng dẫn chẩn đoán và điều trị của <strong>Bộ Y Tế Việt Nam</strong> phối hợp với các hiệp hội quốc tế:
                      </p>
                      <ul style={{ paddingLeft: '16px', margin: '8px 0', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <li><strong>Hen suyễn:</strong> GINA (Global Initiative for Asthma).</li>
                        <li><strong>Đau ngực / Tim mạch:</strong> ESC (European Society of Cardiology).</li>
                        <li><strong>Đái tháo đường:</strong> ADA (American Diabetes Association).</li>
                      </ul>
                      <p style={{ margin: '14px 0 0 0', fontStyle: 'italic', color: '#dc2626' }}>
                        * Lưu ý: Các sơ đồ chỉ mang tính hỗ trợ chẩn đoán nhanh, không thay thế cho quyết định lâm sàng cuối cùng của bác sĩ điều trị dựa trên bệnh cảnh thực tế.
                      </p>
                    </div>
                  </div>

                </div>
              )}
            </div>
          )}

          {/* TAB 5: Giới thiệu */}
          {activeTab === 'about' && (
            <div className="about-tab-view animate-fade-in">
              <div className="about-card">
                <h2>Về MedRAG Assistant</h2>
                <p className="intro-lead">Hệ thống trợ lý y tế thông minh tích hợp công nghệ RAG (Retrieval-Augmented Generation) và sơ đồ chẩn đoán lâm sàng tương tác.</p>
                
                <div className="about-features-grid">
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Truy vấn y văn chính xác</h4>
                      <p>Tìm kiếm kết hợp (Dense + Sparse Search) cùng bộ tái xếp hạng (Cross-Encoder) cho kết quả chính xác theo đoạn văn bản và số trang cụ thể.</p>
                    </div>
                  </div>
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Sơ đồ chẩn đoán tương tác</h4>
                      <p>Tích hợp lưu đồ chẩn đoán lâm sàng giúp đưa ra các quyết định xử lý nhanh dựa trên các dấu hiệu lâm sàng của bệnh nhân.</p>
                    </div>
                  </div>
                  <div className="feature-item">
                    <CheckCircle2 size={18} className="feat-check" />
                    <div>
                      <h4>Bảo mật dữ liệu tối đa</h4>
                      <p>Mô hình trích xuất vector và cơ sở dữ liệu vector chạy hoàn toàn trên máy cục bộ, bảo vệ thông tin chuyên môn y khoa.</p>
                    </div>
                  </div>
                </div>

                <div className="about-system-specs">
                  <h3>Thông số kỹ thuật hệ thống</h3>
                  <ul>
                    <li><strong>Mô hình ngôn ngữ lớn (LLM):</strong> DeepSeek Chat (qua API)</li>
                    <li><strong>Mô hình trích xuất vector (Dense):</strong> sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (chạy cục bộ)</li>
                    <li><strong>Mô hình tái xếp hạng (Reranker):</strong> cross-encoder/ms-marco-MiniLM-L-6-v2 (chạy cục bộ)</li>
                    <li><strong>Cơ sở dữ liệu vector:</strong> LangChain ChromaDB</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: Cài đặt */}
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
          <span>Thông tin chỉ mang tính chất tham khảo lâm sàng học thuật, quyết định điều trị cuối cùng thuộc về bác sĩ chuyên môn.</span>
        </footer>
      </div>
    </div>
  );
}
