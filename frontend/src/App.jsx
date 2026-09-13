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
import IntroExperience from './components/IntroExperience';
import { readSseStream } from './lib/sse';
import SettingsDialog from './components/SettingsDialog';
import AccountMenu from './components/AccountMenu';
import AuthedImage from './components/AuthedImage';
import EditProfileDialog from './components/EditProfileDialog';
import useSettings from './components/useSettings';
import useProfiles from './components/useProfiles';
import DocumentAnnotator from './components/DocumentAnnotator';
import CompareView from './components/CompareView';
import { SimilarQuestions, SearchHistoryDialog } from './components/SearchHistory';
import useAuth from './components/useAuth';
import LoginScreen from './components/LoginScreen';
import DashboardView from './components/DashboardView';
import RemindersView from './components/RemindersView';
import ExportPdfDialog from './components/ExportPdfDialog';
import ClinicAdminDialog, { ChangePasswordDialog } from './components/ClinicAdmin';
import DiagnosisTreeView from './components/DiagnosisTreeView';
import { apiSend, apiDownload } from './lib/apiClient';
import {
  Search,
  Pill,
  Info,
  Moon,
  Sun,
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
  Check,
  Stethoscope,
  Loader2,
  Sparkles,
  AlertCircle,
  BookOpen,
  Library,
  Users,
  GitBranch,
  Activity,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Plus,
  Mic,
  Square,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  MoreHorizontal,
  Pin,
  PinOff,
  PencilLine,
  Share2,
  CheckCircle2,
  LayoutGrid,
  List,
  Download,
  Eye,
  FileText,
  Bell,
  Phone,
  Mail,
  MapPin,
  Scale,
  Ruler,
  Ban,
  UsersRound,
  Heart,
  Thermometer,
  Paperclip,
  Minus,
  UserRound,
  Image as ImageIcon,
  Calendar,
  Printer,
  ClipboardList,
  FlaskConical,
  Waves,
  ScanLine,
  RotateCcw,
  Target,
  Clock,
  Utensils,
  ShieldAlert,
  History,
  GitCompareArrows,
  BarChart3,
  BellRing,
  ShieldCheck,
  KeyRound,
  Lock
} from 'lucide-react';

const uid = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`);

/**
 * Trường lâm sàng này có nội dung thật hay chỉ là chỗ trống?
 *
 * Không thể chỉ kiểm tra chuỗi rỗng. Trong cơ sở dữ liệu hiện có bệnh nhân với
 * `allergies` bằng đúng chuỗi "Không có" — một chuỗi truthy. Nếu chỉ xét truthy
 * thì bệnh nhân KHÔNG dị ứng vẫn hiện ô đỏ, và màu đỏ lại mất hết sức cảnh báo
 * đúng như trước khi sửa.
 *
 * Cố ý KHÔNG đoán xa hơn: chỉ những câu phủ định nguyên vẹn, viết trọn, mới bị
 * coi là trống. "Không dị ứng penicillin đã biết" vẫn là thông tin lâm sàng
 * thật và phải giữ nguyên màu cảnh báo.
 */
const NO_DATA_PHRASES = new Set([
  '', '-', '--', 'n/a', 'na',
  'không', 'không có', 'khong', 'khong co',
  'chưa có', 'chua co', 'chưa ghi', 'chua ghi',
  'chưa có tiền sử bệnh', 'chua co tien su benh',
  'không rõ', 'khong ro',
]);

const hasClinicalValue = (value) => {
  if (value == null) return false;
  const text = String(value).trim();
  if (!text) return false;
  const normalized = text.toLowerCase().replace(/[.,;:!]+$/, '').trim();
  return !NO_DATA_PHRASES.has(normalized);
};
const MAX_PINNED_CONVERSATIONS = 3;

// --- Hồ sơ bệnh nhân (patient profile) helpers ---
const formatDateVN = (isoDate) => {
  if (!isoDate) return '--';
  const d = new Date(isoDate.length === 10 ? `${isoDate}T00:00:00` : isoDate);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

const formatFollowupDueLabel = (daysDiff) => {
  if (daysDiff < 0) return `Quá hạn ${Math.abs(daysDiff)} ngày`;
  if (daysDiff === 0) return 'Hôm nay';
  if (daysDiff === 1) return 'Ngày mai';
  return `Còn ${daysDiff} ngày`;
};

const formatTimeVN = (isoDateTime) => {
  if (!isoDateTime || isoDateTime.length <= 10) return '';
  const d = new Date(isoDateTime);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
};

const TREATMENT_STATUS_META = {
  in_progress: { label: 'Đang điều trị', className: 'pp-status-progress' },
  completed: { label: 'Hoàn thành', className: 'pp-status-done' },
};

// Confidence-score → label/color mapping shared by the primary diagnosis badge and the
// Chẩn đoán phân biệt (Top 5) table's "Độ tin cậy" column.
const confidenceMeta = (score) => {
  const n = score || 0;
  if (n >= 70) return { label: 'Cao', className: 'pp-confidence-high' };
  if (n >= 40) return { label: 'Trung bình', className: 'pp-confidence-mid' };
  return { label: 'Thấp', className: 'pp-confidence-low' };
};

// Splits a primary diagnosis string like "Viêm họng cấp không đặc hiệu (J02.9)" into
// its ICD-10 code and disease name for the Kế hoạch điều trị diagnosis card.
const parseDiagnosisPrimary = (str) => {
  const s = (str || '').trim();
  const m = s.match(/^(.*)\(([A-Z][0-9][0-9A-Z.]*)\)\s*$/);
  return m ? { name: m[1].trim(), code: m[2].trim() } : { name: s, code: '' };
};

const PATIENT_PROFILE_TABS = [
  { id: 'overview', label: 'Tổng quan' },
  { id: 'history', label: 'Lịch sử khám bệnh' },
  { id: 'treatment', label: 'Kế hoạch điều trị' },
  { id: 'documents', label: 'Tài liệu đính kèm' },
  { id: 'notes', label: 'Ghi chú' },
];

const NOTES_VITALS_FIELDS = [
  { key: 'pulse', label: 'Mạch', unit: 'lần / phút', placeholder: '88' },
  { key: 'blood_pressure', label: 'Huyết áp', unit: 'mm Hg', placeholder: '120 / 80' },
  { key: 'resp_rate', label: 'Nhịp thở', unit: 'lần / phút', placeholder: '18' },
  { key: 'temperature', label: 'Nhiệt độ', unit: '°C', placeholder: '37' },
];

const NOTES_EXAM_FIELDS = [
  { key: 'general_exam', label: 'Khám tổng quát', placeholder: 'Bệnh nhân tỉnh, tiếp xúc tốt, da niêm hồng, hạch ngoại vi không sờ chạm, không phù, tuyến giáp không to.' },
  { key: 'cardio_exam', label: 'Khám tim mạch', placeholder: 'Tim T1, T2 đều rõ, không âm thổi bệnh lý.' },
  { key: 'resp_exam', label: 'Khám hô hấp', placeholder: 'Phổi trong, không rales.' },
  { key: 'abdomen_exam', label: 'Khám bụng', placeholder: 'Bụng mềm, không điểm đau khu trú.' },
  { key: 'other_exam', label: 'Các cơ quan khác', placeholder: 'Hiện tại chưa ghi nhận bất thường.' },
];

const NOTES_ENT_FIELDS = [
  { key: 'ent_ear', label: 'Tai', placeholder: 'Đau tai, chảy nước tai, ngứa tai, ù tai, nghe kém, tiếng vo ve.' },
  { key: 'ent_nose', label: 'Mũi', placeholder: 'Sổ mũi (nếu có sổ mũi, nước mũi màu gì), nghẹt mũi, ngứa mũi, hắt xì, mất mùi.' },
  { key: 'ent_throat', label: 'Họng', placeholder: 'Đau họng, vướng đàm, ho (khan hay có đàm, nếu có đàm thì đàm màu gì), khô họng, rát họng, nuốt vướng, khàn tiếng (nếu có, thì bao lâu rồi).' },
  { key: 'ent_other', label: 'Hỏi thêm', placeholder: 'Nhức đầu, chóng mặt, buồn nôn.' },
  { key: 'ent_scope_nose', label: 'Nội soi mũi', placeholder: 'Niêm mạc sung huyết, dịch nhầy, mủ khe mũi giữa, vòm mũi họng sung huyết, dịch nhầy, mủ. V.A.' },
  { key: 'ent_scope_ear', label: 'Nội soi tai', placeholder: 'Ống tai, màng nhĩ.' },
  { key: 'ent_scope_throat', label: 'Nội soi họng', placeholder: 'Dây thanh, xoang lê, amidan, đáy lưỡi có lympho quá phát.' },
];

const NOTES_DRAFT_DEFAULT = {
  visit_date: '',
  reason_for_visit: '',
  vitals: { pulse: '', blood_pressure: '', resp_rate: '', temperature: '' },
  general_exam: '', cardio_exam: '', resp_exam: '', abdomen_exam: '', other_exam: '',
  ent_ear: '', ent_nose: '', ent_throat: '', ent_other: '', ent_scope_nose: '', ent_scope_ear: '', ent_scope_throat: '',
};

const NOTE_STATUS_META = {
  draft: { label: 'Nháp', className: 'pp-status-progress' },
  final: { label: 'Đã lưu', className: 'pp-status-done' },
};

// Converts a saved clinical-note record (from the API) into the flat draft shape the
// "Ghi chú" form/state uses — the two already share field names, this just fills gaps.
const noteToDraft = (note) => ({
  visit_date: note.visit_date || '',
  reason_for_visit: note.reason_for_visit || '',
  vitals: {
    pulse: note.vitals?.pulse || '', blood_pressure: note.vitals?.blood_pressure || '',
    resp_rate: note.vitals?.resp_rate || '', temperature: note.vitals?.temperature || '',
  },
  general_exam: note.general_exam || '', cardio_exam: note.cardio_exam || '', resp_exam: note.resp_exam || '',
  abdomen_exam: note.abdomen_exam || '', other_exam: note.other_exam || '',
  ent_ear: note.ent_ear || '', ent_nose: note.ent_nose || '', ent_throat: note.ent_throat || '', ent_other: note.ent_other || '',
  ent_scope_nose: note.ent_scope_nose || '', ent_scope_ear: note.ent_scope_ear || '', ent_scope_throat: note.ent_scope_throat || '',
});

const stripDiacriticsVN = (str) => (str || '')
  .normalize('NFD')
  .replace(/[̀-ͯ]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLowerCase();

const DOC_CATEGORY_META = {
  lab: { label: 'Xét nghiệm', icon: FlaskConical, pill: 'pp-pill-orange' },
  imaging: { label: 'Hình ảnh', icon: ImageIcon, pill: 'pp-pill-green' },
  xray: { label: 'X-quang', icon: ScanLine, pill: 'pp-pill-blue' },
  endoscopy: { label: 'Nội soi', icon: Stethoscope, pill: 'pp-pill-purple' },
  ultrasound: { label: 'Siêu âm', icon: Waves, pill: 'pp-pill-pink' },
  other: { label: 'Tài liệu khác', icon: FileText, pill: 'pp-pill-slate' },
};

const DOC_CATEGORY_ORDER = ['lab', 'imaging', 'xray', 'endoscopy', 'ultrasound', 'other'];

const classifyAttachmentCategory = (att) => {
  const name = stripDiacriticsVN(att.original_name || '');
  const ext = (att.file_type || '').toUpperCase();
  if (name.includes('x-quang') || name.includes('x quang') || name.includes('xquang') || name.includes('x-ray') || name.includes('xray')) return 'xray';
  if (name.includes('sieu am')) return 'ultrasound';
  if (name.includes('noi soi')) return 'endoscopy';
  if (name.includes('xet nghiem') || name.includes('ket qua xn') || name.includes('ket qua xet')) return 'lab';
  if (['JPG', 'JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF'].includes(ext)) return 'imaging';
  return 'other';
};

const DOC_FILE_HUE = {
  PDF: 'red',
  DOC: 'blue',
  DOCX: 'blue',
  XLS: 'green',
  XLSX: 'green',
};

const getDocFileHue = (ext) => DOC_FILE_HUE[(ext || '').toUpperCase()] || 'slate';

const VITAL_META = {
  pulse: { label: 'Mạch', unit: 'lần/phút', icon: Heart, color: '#ec4899' },
  blood_pressure: { label: 'Huyết áp', unit: 'mmHg', icon: Activity, color: '#ef4444' },
  resp_rate: { label: 'Nhịp thở', unit: 'lần/phút', icon: Waves, color: '#3b82f6' },
  temperature: { label: 'Nhiệt độ', unit: '°C', icon: Thermometer, color: '#f59e0b' },
};

const formatFileSize = (bytes) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const DRUG_QUICK_SUGGESTIONS = [
  "Amoxicilin",
  "Thuốc hạ huyết áp",
  "PPI",
  "Insulin",
  "Thuốc chống đông",
  "Paracetamol",
  "Cephalosporin"
];

const DEFAULT_PARACETAMOL_REPORT = {
  drug_name: 'Paracetamol (Acetaminophen)',
  subtitle: 'Thuốc giảm đau – hạ sốt không opioid',
  created_at: '29/08/2026 14:30',
  model_used: 'Deepseek',
  confidence_overall: 'Cao',
  sections: [
    {
      id: '1',
      title: '1. Tổng quan',
      confidence: 'Cao',
      content: 'Paracetamol (Acetaminophen) là thuốc giảm đau và hạ sốt thuộc nhóm thuốc giảm đau – hạ sốt không opioid [1]. Thuốc có tác dụng chủ yếu trên hệ thần kinh trung ương, ít tác dụng chống viêm [1][2].'
    },
    {
      id: '2',
      title: '2. Chỉ định',
      confidence: 'Cao',
      content: '• Giảm đau nhẹ đến vừa: đau đầu, đau răng, đau cơ, đau bụng kinh, đau do cảm cúm [1][3].\n• Hạ sốt trong các trường hợp sốt do nhiễm virus, cảm cúm, sau tiêm chủng [2].\n• Thay thế cho Aspirin ở bệnh nhân không dung nạp NSAID [1].'
    },
    {
      id: '3',
      title: '3. Liều dùng',
      confidence: 'Cao',
      content: '**Người lớn và trẻ em ≥ 12 tuổi:**\n• Liều thông thường: 500 – 1.000 mg/lần, mỗi 4–6 giờ khi cần thiết [1][2].\n• Liều tối đa: 4.000 mg/ngày (không vượt quá 8 viên 500 mg) [3].\n\n**Trẻ em (dưới 12 tuổi):**\n• 10 – 15 mg/kg/lần, cách nhau 4–6 giờ (tối đa không quá 60 mg/kg/ngày) [1].'
    },
    {
      id: '4',
      title: '4. Chống chỉ định',
      confidence: 'Cao',
      content: '• Quá mẫn cảm với Paracetamol hoặc bất kỳ thành phần nào của thuốc [1].\n• Bệnh nhân suy gan nặng, bệnh gan tiến triển hoặc viêm gan virus cấp [2][3].\n• Bệnh nhân thiếu hụt enzym Glucose-6-phosphate dehydrogenase (G6PD) [1].'
    },
    {
      id: '5',
      title: '5. Tác dụng phụ',
      confidence: 'Cao',
      content: '• Thường gặp: Ban da nhẹ, mày đay, ngứa [2].\n• Hiếm gặp: Giảm bạch cầu trung tính, giảm tiểu cầu, phản ứng da nghiêm trọng (hội chứng Stevens-Johnson, TEN) [1].\n• Độc tính trên gan: Nguy cơ hoại tử tế bào gan cấp tính khi dùng quá liều hoặc dùng kèm rượu [3].'
    },
    {
      id: '6',
      title: '6. Tương tác thuốc',
      confidence: 'Cao',
      content: '• **Rượu (Ethanol):** Uống nhiều rượu làm tăng cảm ứng enzym CYP2E1 tạo chất độc NAPQI gây tổn thương gan nặng [1][2].\n• **Thuốc chống đông (Warfarin):** Dùng Paracetamol liều cao kéo dài làm tăng nhẹ tác dụng chống đông và nguy cơ chảy máu [3].\n• **Thuốc cảm ứng enzym gan (Phenobarbital, Phenytoin, Carbamazepine, Isoniazid):** Tăng độc tính trên gan của Paracetamol [2].'
    },
    {
      id: '7',
      title: '7. Thận trọng',
      confidence: 'Cao',
      content: '• **Tránh quá liều trùng lặp:** Kiểm tra thành phần các biệt dược điều trị cảm cúm phối hợp để tránh dùng quá liều Paracetamol vô ý [1].\n• **Bệnh nhân nguy cơ:** Thận trọng ở người suy gan nhẹ/vừa, suy thận nặng, người nghiện rượu mãn tính, suy dinh dưỡng hoặc mất nước [3].\n• **Phụ nữ có thai:** Được coi là thuốc giảm đau, hạ sốt lựa chọn hàng đầu an toàn trong thai kỳ khi dùng ở liều điều trị thấp nhất có hiệu quả và thời gian ngắn nhất (FDA Category B) [1][2].\n• **Phụ nữ cho con bú:** Thuốc bài tiết qua sữa mẹ với nồng độ rất thấp, an toàn khi cho con bú [2].'
    },
    {
      id: '8',
      title: '8. Dạng bào chế',
      confidence: 'Cao',
      content: '• Viên nén, viên nang: 325 mg, 500 mg, 650 mg [1].\n• Viên sủi bọt: 500 mg, 1.000 mg (Efferalgan, Panadol) [1].\n• Gói bột/cốm sủi pha hỗn dịch: 80 mg, 150 mg, 250 mg (chuyên biệt cho trẻ nhỏ) [2].\n• Dung dịch tiêm truyền: 10 mg/ml (Chai 100 ml tương đương 1.000 mg) [3].\n• Viên đạn đặt trực tràng: 80 mg, 150 mg, 300 mg [1].'
    },
    {
      id: '9',
      title: '9. Bảo quản',
      confidence: 'Cao',
      content: '• Bảo quản ở nhiệt độ dưới 30°C, nơi khô ráo, tránh ánh sáng trực tiếp và ẩm ướt [1].\n• Để xa tầm tay trẻ em [1].'
    }
  ],
  quick_summary: [
    { type: 'success', text: 'Giảm đau, hạ sốt hiệu quả' },
    { type: 'success', text: 'An toàn nếu dùng đúng liều' },
    { type: 'warning', text: 'Nguy cơ độc gan khi quá liều' },
    { type: 'danger', text: 'Tránh dùng chung với rượu' }
  ],
  sources: [
    {
      id: '1',
      doc_name: 'THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf',
      file_size: 'PDF • 61.8 MB',
      page_num: 'Trang 21',
      snippet: 'Chuyên luận Dược học & Biệt dược: Paracetamol (Acetaminophen) phối hợp và đơn chất. Chỉ định hạ sốt, giảm đau nhẹ đến vừa. Liều người lớn 500-1000mg/lần, tối đa 4g/ngày. Chống chỉ định suy gan nặng, thiếu hụt men G6PD.',
      text: '### PARACETAMOL - DƯỢC THƯ BIỆT DƯỢC VÀ CÁCH SỬ DỤNG (Trang 21)\n\n**Tác dụng - Dược lý:** Thuốc giảm đau - hạ sốt hữu hiệu thay thế aspirin. Không gây kích ứng niêm mạc dạ dày hoặc ức chế kết tập tiểu cầu.\n\n**Chỉ định:** Các chứng đau từ nhẹ đến trung bình (nhức đầu, đau răng, đau nhức cơ xương khớp, đau sau phẫu thuật) và các trường hợp sốt do mọi nguyên nhân.\n\n**Liều dùng - Cách dùng:** Người lớn và trẻ em trên 12 tuổi: uống 500–1.000 mg mỗi 4–6 giờ khi cần; không quá 4.000 mg/24 giờ.\n\n**Chống chỉ định:** Người bệnh quá mẫn với paracetamol; suy giảm chức năng tế bào gan nặng; thiếu máu nhiều lần.',
      score: 0.98
    },
    {
      id: '2',
      doc_name: 'THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf',
      file_size: 'PDF • 61.8 MB',
      page_num: 'Trang 18',
      snippet: 'Dạng thuốc - Trình bày: Viên nén 500mg, viên sủi bọt, bột cốm hòa tan. Thận trọng không dùng cùng lúc nhiều biệt dược chứa cùng hoạt chất để tránh ngộ độc gan cấp tính do quá liều.',
      text: '### PARACETAMOL - DẠNG THUỐC VÀ TRÌNH BÀY (Trang 18)\n\n**Dạng thuốc:** Viên nén, viên nang 325mg, 500mg; viên sủi bọt Efferalgan/Panadol 500mg, 1000mg; gói thuốc cốm/bột sủi 80mg, 150mg, 250mg cho trẻ em.\n\n**Lưu ý:** Tuyệt đối không dùng chung với rượu hoặc các biệt dược cảm cúm khác chứa paracetamol để tránh tích lũy độc tố NAPQI gây hoại tử tế bào gan.',
      score: 0.95
    },
    {
      id: '3',
      doc_name: 'THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf',
      file_size: 'PDF • 61.8 MB',
      page_num: 'Trang 19',
      snippet: 'Lưu ý - Thận trọng: Phụ nữ có thai và cho con bú có thể sử dụng ở liều điều trị ngắn nhất có hiệu quả. Cần thận trọng điều chỉnh liều ở người suy gan, suy thận nặng.',
      text: '### PARACETAMOL - THẬN TRỌNG VÀ TƯƠNG TÁC (Trang 19)\n\n**Phụ nữ có thai & Cho con bú:** Thuốc qua được hàng rào nhau thai và bài tiết vào sữa mẹ với lượng rất nhỏ; là lựa chọn ưu tiên an toàn trong thai kỳ và thời kỳ nuôi con bú khi dùng đúng liều chỉ định.\n\n**Tương tác thuốc:** Dùng dài ngày liều cao có thể làm tăng nhẹ tác dụng chống đông của coumarin và dẫn chất indandion.',
      score: 0.92
    },
    {
      id: '4',
      doc_name: 'THUOC-BIET-DUOC-VA-CACH-SU-DUNG.pdf',
      file_size: 'PDF • 61.8 MB',
      page_num: 'Trang 178',
      snippet: 'Biệt dược phối hợp: Paracetamol kết hợp Cafein, Codein, kháng histamin. Cần kiểm tra kỹ thành phần tổng liều tránh vượt quá ngưỡng an toàn điều trị.',
      text: '### PARACETAMOL - CÁC BIỆT DƯỢC PHỐI HỢP (Trang 178)\n\nCác biệt dược phối hợp phổ biến: Paracetamol + Cafein (giảm mệt mỏi, tăng hấp thu), Paracetamol + Codein (giảm đau bậc 2), Paracetamol + Chlorpheniramin (điều trị triệu chứng cảm sổ mũi).',
      score: 0.89
    }
  ]
};

export default function App() {
  // Read-only "shared conversation" route: /?share=<id> (query-based so any static host works)
  const shareViewId = new URLSearchParams(window.location.search).get('share');

  // Navigation & Page state
  const [activeTab, setActiveTab] = useState('medicine'); // Default to 'medicine' tab per user focus
  // Every persisted preference behind the settings dialog lives in this hook.
  const settings = useSettings();
  const { isDarkMode, libraryViewMode, setLibraryViewMode, notifyEnabled, notifyRecheck } = settings;
  // Phiên đăng nhập & phân quyền — quyết định thấy hồ sơ của ai, sửa được gì.
  const auth = useAuth();
  const { user: currentUser, permissions } = auth;
  // Doctor identity (name/username/avatar) is API-backed — see components/useProfiles.js
  const profiles = useProfiles();
  const doctorName = currentUser?.display_name || profiles.activeProfile?.display_name || 'BS. Hà Thanh Hùng';
  const [clinicAdminOpen, setClinicAdminOpen] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const [exportPdfOpen, setExportPdfOpen] = useState(false);
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
    fetchPatients();
    fetchNotifications();
  }, [auth.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [showSourcesPanel, setShowSourcesPanel] = useState(true);

  // Core Data State
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // "Thư viện" tab — ChatGPT Library-style gallery state
  const [librarySearch, setLibrarySearch] = useState('');
  const [librarySortBy, setLibrarySortBy] = useState('newest'); // 'newest' | 'oldest' | 'name' | 'pages'
  const [deleteDocTarget, setDeleteDocTarget] = useState(null); // doc_name | null
  const [libraryPreview, setLibraryPreview] = useState(null); // { doc_name, page_num, text } | null
  // Reader: xem ảnh scan trang gốc thay cho văn bản OCR (đối chiếu trích dẫn)
  const [readerShowScan, setReaderShowScan] = useState(false);

  // Lịch sử tra cứu (tái sử dụng kết quả cũ thay vì hỏi lại AI)
  const [historyOpen, setHistoryOpen] = useState(false);
  // { doc_name: số đoạn đã tô sáng }
  const [highlightCounts, setHighlightCounts] = useState({});
  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('deepseek_api_key') || '');
  const [bannerMessage, setBannerMessage] = useState('');
  const [backendHasKey, setBackendHasKey] = useState(false);

  // "Cài đặt" tab state — doctor profile (moved here from the header pill) + ChatGPT-style preference toggles
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editProfileOpen, setEditProfileOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState('general');
  const doctorNamePlain = doctorName.replace(/^BS\.?\s*/i, '').trim(); // "doctor_name" fields store the bare name, no "BS." prefix

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

  // Dynamic state for patients (hồ sơ bệnh nhân)
  const [patients, setPatients] = useState([]);
  const [selectedPatientId, setSelectedPatientId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [patientDetailLoading, setPatientDetailLoading] = useState(false);
  const [patientSearchQuery, setPatientSearchQuery] = useState('');
  const [patientSearchOpen, setPatientSearchOpen] = useState(false);
  const [patientSearchResults, setPatientSearchResults] = useState([]);
  const [patientProfileTab, setPatientProfileTab] = useState('overview');
  const [isAddPatientOpen, setIsAddPatientOpen] = useState(false);
  const [nextPatientCode, setNextPatientCode] = useState('');
  const [isEditingQuickNote, setIsEditingQuickNote] = useState(false);
  const [quickNoteDraft, setQuickNoteDraft] = useState('');

  // "Ghi chú" tab (clinical visit notes, backed by /api/patients/{id}/notes) state
  const [activeNoteId, setActiveNoteId] = useState(null);
  const [isNoteFormOpen, setIsNoteFormOpen] = useState(false); // full form: creating new, or bulk-editing an existing note
  const [noteFormDraft, setNoteFormDraft] = useState(NOTES_DRAFT_DEFAULT);
  const [isSavingNote, setIsSavingNote] = useState(false);

  // Notification bell (nhắc lịch tái khám)
  const [notifications, setNotifications] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [dismissedNotifIds, setDismissedNotifIds] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('notif_dismissed_ids') || '[]'));
    } catch {
      return new Set();
    }
  });

  // "Lịch sử khám bệnh" tab state
  const [historyDateRange, setHistoryDateRange] = useState('all');
  const [historyStatus, setHistoryStatus] = useState('all');
  const [historyDiagnosisSearch, setHistoryDiagnosisSearch] = useState('');
  const [historyDoctor, setHistoryDoctor] = useState('all');
  const [expandedHistoryVisitId, setExpandedHistoryVisitId] = useState(null);

  // "Tạo kế hoạch mới" side panel state — mirrors the 4 feature cards on the "Kế hoạch điều trị" tab
  const [isAddVisitOpen, setIsAddVisitOpen] = useState(false);
  const [isSavingVisit, setIsSavingVisit] = useState(false);
  const [newVisitDate, setNewVisitDate] = useState('');
  const [newVisitDoctor, setNewVisitDoctor] = useState('');
  const [newVisitTitle, setNewVisitTitle] = useState('');
  // 1. Chẩn đoán
  const [newVisitSymptomInput, setNewVisitSymptomInput] = useState('');
  const [newVisitSymptoms, setNewVisitSymptoms] = useState([]);
  const [newVisitDiagnosis, setNewVisitDiagnosis] = useState('');
  const [newVisitDiagnosisSecondary, setNewVisitDiagnosisSecondary] = useState('');
  const [newVisitExamFindings, setNewVisitExamFindings] = useState('');
  // 2. Kế hoạch điều trị
  const [newVisitGoals, setNewVisitGoals] = useState('');
  const [newVisitTreatmentMethod, setNewVisitTreatmentMethod] = useState('');
  const [newVisitProtocolDuration, setNewVisitProtocolDuration] = useState('');
  const [newVisitDietRegimen, setNewVisitDietRegimen] = useState('');
  const [newVisitPrecautions, setNewVisitPrecautions] = useState('');
  const [newVisitFollowupPurpose, setNewVisitFollowupPurpose] = useState('');
  const [newVisitFollowupDate, setNewVisitFollowupDate] = useState('');
  const [newVisitTreatmentInstructions, setNewVisitTreatmentInstructions] = useState('');
  // 3. Đơn thuốc
  const [newVisitMedications, setNewVisitMedications] = useState([]);
  const [isAddingVisitMedication, setIsAddingVisitMedication] = useState(false);
  const [visitMedDraft, setVisitMedDraft] = useState({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' });
  const [newVisitNoDrugRecommendations, setNewVisitNoDrugRecommendations] = useState('');
  // 4. Hướng dẫn cho bệnh nhân
  const [newVisitCareInstructions, setNewVisitCareInstructions] = useState('');

  // "Tài liệu đính kèm" tab state
  const [docSearch, setDocSearch] = useState('');
  const [docCategory, setDocCategory] = useState('all');
  const [docDateRange, setDocDateRange] = useState('all');
  const [docStatus, setDocStatus] = useState('all');
  const [docSort, setDocSort] = useState('newest');
  const [docView, setDocView] = useState('grid');
  const [docVisibleCount, setDocVisibleCount] = useState(8);

  // "Điều trị" tab (treatment plan) state
  const [activeTreatmentVisitId, setActiveTreatmentVisitId] = useState(null);
  const [aiSuggestLoading, setAiSuggestLoading] = useState(false);
  const [aiReasoningNote, setAiReasoningNote] = useState('');
  const [aiAgentTrace, setAiAgentTrace] = useState([]);
  const [aiAgentSources, setAiAgentSources] = useState([]);
  const [aiAgentTraceExpanded, setAiAgentTraceExpanded] = useState(false);
  const [isEditingDiagnosis, setIsEditingDiagnosis] = useState(false);
  const [diagnosisDraft, setDiagnosisDraft] = useState({ primary: '', differentials: '', exam: '' });
  const [isEditingDiagnosisNote, setIsEditingDiagnosisNote] = useState(false);
  const [diagnosisNoteDraft, setDiagnosisNoteDraft] = useState('');
  const [showDiagnosisReasoning, setShowDiagnosisReasoning] = useState(false);
  const [isEditingNoDrug, setIsEditingNoDrug] = useState(false);
  const [noDrugDraft, setNoDrugDraft] = useState('');
  const [isEditingCare, setIsEditingCare] = useState(false);
  const [careDraft, setCareDraft] = useState('');
  const [isEditingFollowup, setIsEditingFollowup] = useState(false);
  const [followupDraft, setFollowupDraft] = useState({ date: '', purpose: '' });
  const [isEditingPlan, setIsEditingPlan] = useState(false);
  const [planDraft, setPlanDraft] = useState({ goals: '', protocol_duration: '', treatment_method: '', diet_regimen: '', precautions: '' });
  const [isAddingMedication, setIsAddingMedication] = useState(false);
  const [medDraft, setMedDraft] = useState({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' });

  // Form states for the "Thêm bệnh nhân" panel
  const [newPatName, setNewPatName] = useState('');
  const [newPatGender, setNewPatGender] = useState('Nam');
  const [newPatPhone, setNewPatPhone] = useState('');
  const [newPatEmail, setNewPatEmail] = useState('');
  const [newPatAddress, setNewPatAddress] = useState('');
  const [newPatBloodType, setNewPatBloodType] = useState('');
  const [newPatHeight, setNewPatHeight] = useState(170);
  const [newPatWeight, setNewPatWeight] = useState(60);
  const [newPatDiagnosis, setNewPatDiagnosis] = useState('');
  const [newPatMedHistory, setNewPatMedHistory] = useState('');
  const [newPatFamilyHistory, setNewPatFamilyHistory] = useState('');
  const [newPatAllergiesNotes, setNewPatAllergiesNotes] = useState('');
  const [newPatMedications, setNewPatMedications] = useState([]);
  const [isAddingPatMedication, setIsAddingPatMedication] = useState(false);
  const [patMedDraft, setPatMedDraft] = useState({ name: '', dosage: '', form: '', frequency: '', instructions: '' });
  const [newPatNoDrugRecommendations, setNewPatNoDrugRecommendations] = useState('');
  const [newPatCareInstructions, setNewPatCareInstructions] = useState('');
  const [isSavingPatient, setIsSavingPatient] = useState(false);

  // "Thuốc" (medicine lookup & AI report) state
  const [drugQuery, setDrugQuery] = useState('');
  const [drugLoading, setDrugLoading] = useState(false);
  const [drugReport, setDrugReport] = useState(DEFAULT_PARACETAMOL_REPORT);
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

  // "Bệnh nhân" linking section on the Diagnosis Tree tab — lets the doctor tie this
  // diagnosis session to an existing patient record (or flag it as a new patient),
  // then hand the results off to the Patients tab via "Cập nhật bệnh".
  const [diagPatientQuery, setDiagPatientQuery] = useState('');
  const [diagPatientSearchOpen, setDiagPatientSearchOpen] = useState(false);
  const [diagPatientResults, setDiagPatientResults] = useState([]);
  const [diagSelectedPatient, setDiagSelectedPatient] = useState(null);
  // Non-null while a diagnosis session is being handed off to the Patients tab — read by
  // handleSaveNewVisit to know it should redirect into the Điều trị tab instead of the
  // regular "expand this visit in Lịch sử" behavior.
  const [diagHandoffPayload, setDiagHandoffPayload] = useState(null);

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

  const makeWelcomeMessage = () => ({
    role: 'assistant',
    text: 'Ba đọc phần "Giới thiệu" để biết cách sử dụng web.',
    time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
  });
  const [draftWelcome, setDraftWelcome] = useState(() => [makeWelcomeMessage()]);

  const activeConversation = conversations.find(c => c.id === activeConversationId) || null;
  const messages = activeConversation ? activeConversation.messages : draftWelcome;

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  // Suggested queries for Vietnamese UI
  const suggestions = [
    "Dấu hiệu đe dọa tính mạng của cơn hen phế quản cấp là gì?",
    "Phác đồ xử trí ban đầu cho bệnh nhân nhồi máu cơ tim STEMI?",
    "Khi nào chỉ định insulin ngay cho bệnh nhân đái tháo đường typ 2?"
  ];

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
      setBannerMessage("Cảnh báo: Chưa cấu hình DeepSeek API Key. Hãy cấu hình API Key trong backend hoặc mục Cài đặt để sử dụng tính năng Chat AI phản hồi đầy đủ.");
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

  // Số đoạn đã tô sáng theo từng tài liệu, hiển thị trên thẻ ở Thư viện
  const fetchHighlightCounts = async () => {
    try {
      const res = await fetch('/api/highlights/counts');
      if (res.ok) setHighlightCounts(await res.json());
    } catch (err) {
      console.error("Error fetching highlight counts:", err);
    }
  };

  const fetchPatients = async (search) => {
    try {
      const url = search ? `/api/patients?search=${encodeURIComponent(search)}` : '/api/patients';
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setPatients(data || []);
        return data || [];
      }
    } catch (err) {
      console.error("Error fetching patients:", err);
    }
    return [];
  };

  const fetchPatientDetail = async (id) => {
    if (!id) { setSelectedPatient(null); return; }
    setPatientDetailLoading(true);
    try {
      const res = await fetch(`/api/patients/${id}`);
      if (res.ok) {
        setSelectedPatient(await res.json());
      } else {
        setSelectedPatient(null);
      }
    } catch (err) {
      console.error("Error fetching patient detail:", err);
      setSelectedPatient(null);
    } finally {
      setPatientDetailLoading(false);
    }
  };

  useEffect(() => {
    if (selectedPatientId) fetchPatientDetail(selectedPatientId);
    else setSelectedPatient(null);
  }, [selectedPatientId]);

  // Auto-select the most recent patient once the list has loaded, if none chosen yet
  useEffect(() => {
    if (!selectedPatientId && patients.length > 0) {
      setSelectedPatientId(patients[0].id);
    }
  }, [patients]);

  const handlePatientSearchChange = async (value) => {
    setPatientSearchQuery(value);
    setPatientSearchOpen(true);
    if (!value.trim()) { setPatientSearchResults([]); return; }
    try {
      const res = await fetch(`/api/patients?search=${encodeURIComponent(value)}`);
      if (res.ok) setPatientSearchResults((await res.json()) || []);
    } catch (err) {
      console.error("Error searching patients:", err);
    }
  };

  const handleSelectSearchedPatient = (id) => {
    setSelectedPatientId(id);
    setPatientSearchQuery('');
    setPatientSearchResults([]);
    setPatientSearchOpen(false);
  };

  const fetchNotifications = async () => {
    setNotifLoading(true);
    try {
      const res = await fetch('/api/notifications');
      const data = await res.json();
      setNotifications(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error fetching notifications:", err);
    } finally {
      setNotifLoading(false);
    }
  };

  const dismissNotification = (visitId) => {
    setDismissedNotifIds((prev) => {
      const next = new Set(prev);
      next.add(visitId);
      localStorage.setItem('notif_dismissed_ids', JSON.stringify([...next]));
      return next;
    });
  };

  /** Hoãn / đánh dấu đã khám ngay trên chuông, không phải mở trang nhắc lịch. */
  const actOnNotification = async (n, action, body) => {
    if (!n.reminder_id) { dismissNotification(n.visit_id); return; }
    try {
      await apiSend(`/api/reminders/${n.reminder_id}/${action}`, 'POST', body);
      await fetchNotifications();
    } catch (err) {
      showStatus('error', err.message || 'Không cập nhật được lời nhắc.');
    }
  };

  const handleNotificationClick = (n) => {
    dismissNotification(n.visit_id);
    setSelectedPatientId(n.patient_id);
    setActiveTab('patients');
  };

  const visibleNotifications = notifyRecheck
    ? notifications.filter((n) => !dismissedNotifIds.has(n.visit_id))
    : [];

  const resetAddPatientForm = () => {
    setNewPatName(''); setNewPatGender('Nam');
    setNewPatPhone(''); setNewPatEmail(''); setNewPatAddress('');
    setNewPatBloodType(''); setNewPatHeight(170); setNewPatWeight(60);
    setNewPatDiagnosis(''); setNewPatMedHistory(''); setNewPatFamilyHistory(''); setNewPatAllergiesNotes('');
    setNewPatMedications([]); setIsAddingPatMedication(false);
    setPatMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '' });
    setNewPatNoDrugRecommendations(''); setNewPatCareInstructions('');
  };

  const handleAddPatMedication = () => {
    if (!patMedDraft.name.trim()) return;
    setNewPatMedications(prev => [...prev, { ...patMedDraft }]);
    setPatMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '' });
    setIsAddingPatMedication(false);
  };

  const handleRemovePatMedication = (idx) => {
    setNewPatMedications(prev => prev.filter((_, i) => i !== idx));
  };

  // handoffPayload, when present, comes from a Diagnosis-Tree handoff for a patient that
  // doesn't exist yet (see handleUpdateDisease) — prefills "Chẩn đoán" and "Điều trị ban đầu"
  // so the doctor isn't re-typing what the diagnosis pipeline already produced.
  const openAddPatientModal = async (handoffPayload = null) => {
    resetAddPatientForm();
    setDiagHandoffPayload(handoffPayload);
    if (handoffPayload) {
      setNewPatDiagnosis([handoffPayload.diagnosisPrimary, handoffPayload.diagnosisSecondary].filter(Boolean).join('\n'));
      setNewPatMedications(handoffPayload.medications || []);
      setNewPatNoDrugRecommendations(handoffPayload.noDrugRecommendations || '');
      setNewPatCareInstructions(handoffPayload.careInstructions || '');
    }
    setIsAddPatientOpen(true);
    try {
      const res = await fetch('/api/patients/next-code');
      if (res.ok) setNextPatientCode((await res.json()).code);
    } catch (err) {
      console.error("Error fetching next patient code:", err);
    }
  };

  const handleAddPatient = async (e) => {
    e.preventDefault();
    if (!newPatName.trim()) return;
    setIsSavingPatient(true);
    try {
      const res = await fetch('/api/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newPatName.trim(),
          gender: newPatGender,
          phone: newPatPhone,
          email: newPatEmail,
          address: newPatAddress,
          blood_type: newPatBloodType,
          height_cm: newPatHeight ? parseFloat(newPatHeight) : null,
          weight_kg: newPatWeight ? parseFloat(newPatWeight) : null,
          chronic_conditions: newPatDiagnosis,
          surgical_history: newPatMedHistory,
          family_history: newPatFamilyHistory,
          allergies: newPatAllergiesNotes,
          notes: newPatAllergiesNotes,
          created_by: doctorName
        })
      });

      if (res.ok) {
        const created = await res.json();
        showStatus('success', `Đã thêm hồ sơ bệnh nhân "${created.name}" thành công.`);

        // If the doctor filled in "Điều trị ban đầu" (and this isn't the diagnosis-tree handoff,
        // which creates its own visit right after), save it as the patient's first visit — same
        // mechanism as "+ Thêm lần khám".
        const hasInitialTreatment = newPatMedications.length > 0
          || newPatNoDrugRecommendations.trim()
          || newPatCareInstructions.trim();
        if (hasInitialTreatment && !diagHandoffPayload) {
          try {
            await fetch(`/api/patients/${created.id}/visits`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                visit_date: new Date().toISOString().slice(0, 10),
                title: 'Khám ban đầu',
                doctor_name: doctorNamePlain,
                diagnosis_primary: newPatDiagnosis.trim(),
                medications: newPatMedications,
                no_drug_recommendations: newPatNoDrugRecommendations.trim(),
                care_instructions: newPatCareInstructions.trim(),
                status: 'in_progress',
              })
            });
          } catch (err) {
            console.error("Error creating initial treatment visit:", err);
          }
        }

        resetAddPatientForm();
        setIsAddPatientOpen(false);
        await fetchPatients();
        setSelectedPatientId(created.id);
        if (diagHandoffPayload) {
          prefillVisitFromHandoff(diagHandoffPayload);
          setIsAddVisitOpen(true);
        }
      } else {
        const data = await res.json();
        throw new Error(data.detail || "Không thể thêm bệnh nhân.");
      }
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      setIsSavingPatient(false);
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
        if (selectedPatientId === id) setSelectedPatientId(null);
        fetchPatients();
      } else {
        throw new Error("Không thể xóa bệnh nhân.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const handleSaveQuickNote = async () => {
    if (!selectedPatient) return;
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/note`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: quickNoteDraft, updated_by: doctorName })
      });
      if (res.ok) {
        await res.json();
        await fetchPatientDetail(selectedPatient.id);
        setIsEditingQuickNote(false);
      } else {
        throw new Error("Không thể lưu ghi chú.");
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  // --- "Ghi chú" tab (clinical visit notes) handlers ---
  const openCreateNote = () => {
    setActiveNoteId(null);
    setNoteFormDraft(NOTES_DRAFT_DEFAULT);
    setIsNoteFormOpen(true);
  };

  // Opens the full form to bulk-edit an existing note (draft or already-finalized) — there is
  // no more per-field editing, editing means editing everything at once.
  const openEditNote = (note) => {
    setActiveNoteId(note.id);
    setNoteFormDraft(noteToDraft(note));
    setIsNoteFormOpen(true);
  };

  // Dropdown selection: a draft has no read-only view, so picking one opens it straight into
  // the full form; a finalized note is shown read-only until "Sửa" is clicked (openEditNote).
  const selectNote = (noteId) => {
    const note = (selectedPatient?.notes || []).find(n => n.id === noteId);
    if (note && note.status === 'draft') {
      openEditNote(note);
    } else {
      setActiveNoteId(noteId);
      setIsNoteFormOpen(false);
    }
  };

  const handleNoteFormFieldChange = (key, value) => {
    setNoteFormDraft(d => ({ ...d, [key]: value }));
  };

  const handleNoteFormVitalChange = (key, value) => {
    setNoteFormDraft(d => ({ ...d, vitals: { ...d.vitals, [key]: value } }));
  };

  const handleCancelNoteForm = () => {
    const note = activeNoteId ? (selectedPatient?.notes || []).find(n => n.id === activeNoteId) : null;
    if (note && note.status === 'draft') {
      // A draft has no read-only view, so cancelling just discards unsaved edits in place.
      setNoteFormDraft(noteToDraft(note));
    } else {
      // Editing an already-finalized note, or a brand-new not-yet-saved one: cancel drops
      // back to the read-only view (or the empty state, for a brand-new note).
      setIsNoteFormOpen(false);
      setNoteFormDraft(NOTES_DRAFT_DEFAULT);
    }
  };

  const buildNotePayload = () => ({
    visit_date: noteFormDraft.visit_date,
    reason_for_visit: noteFormDraft.reason_for_visit.trim(),
    vital_pulse: noteFormDraft.vitals.pulse.trim(),
    vital_blood_pressure: noteFormDraft.vitals.blood_pressure.trim(),
    vital_resp_rate: noteFormDraft.vitals.resp_rate.trim(),
    vital_temperature: noteFormDraft.vitals.temperature.trim(),
    general_exam: noteFormDraft.general_exam.trim(),
    cardio_exam: noteFormDraft.cardio_exam.trim(),
    resp_exam: noteFormDraft.resp_exam.trim(),
    abdomen_exam: noteFormDraft.abdomen_exam.trim(),
    other_exam: noteFormDraft.other_exam.trim(),
    ent_ear: noteFormDraft.ent_ear.trim(),
    ent_nose: noteFormDraft.ent_nose.trim(),
    ent_throat: noteFormDraft.ent_throat.trim(),
    ent_other: noteFormDraft.ent_other.trim(),
    ent_scope_nose: noteFormDraft.ent_scope_nose.trim(),
    ent_scope_ear: noteFormDraft.ent_scope_ear.trim(),
    ent_scope_throat: noteFormDraft.ent_scope_throat.trim(),
  });

  const saveNoteForm = async (status) => {
    if (!selectedPatient) return;
    if (status === 'final' && !noteFormDraft.visit_date) {
      showStatus('error', 'Vui lòng nhập ngày khám trước khi lưu ghi chú.');
      return;
    }
    setIsSavingNote(true);
    try {
      const isNew = !activeNoteId;
      const res = await fetch(
        isNew ? `/api/patients/${selectedPatient.id}/notes` : `/api/patients/${selectedPatient.id}/notes/${activeNoteId}`,
        {
          method: isNew ? 'POST' : 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...buildNotePayload(), status }),
        }
      );
      if (res.ok) {
        const saved = await res.json();
        showStatus('success', status === 'draft' ? 'Đã lưu nháp ghi chú.' : 'Đã lưu ghi chú thăm khám.');
        setActiveNoteId(saved.id);
        if (status === 'final') setIsNoteFormOpen(false);
        await fetchPatientDetail(selectedPatient.id);
      } else {
        const data = await res.json();
        throw new Error(data.detail || 'Không thể lưu ghi chú.');
      }
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      setIsSavingNote(false);
    }
  };

  const handleSaveNoteDraft = () => saveNoteForm('draft');
  const handleSaveNoteFinal = () => saveNoteForm('final');

  const handleDeleteNote = async (noteId) => {
    if (!selectedPatient) return;
    if (!confirm('Bạn có chắc chắn muốn xóa ghi chú này?')) return;
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/notes/${noteId}`, { method: 'DELETE' });
      if (res.ok) {
        showStatus('success', 'Đã xóa ghi chú.');
        if (activeNoteId === noteId) { setActiveNoteId(null); setIsNoteFormOpen(false); }
        await fetchPatientDetail(selectedPatient.id);
      } else {
        throw new Error('Không thể xóa ghi chú.');
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  const handleUploadAttachment = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedPatient) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/attachments`, {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        fetchPatientDetail(selectedPatient.id);
      } else {
        throw new Error("Không thể tải lên tệp đính kèm.");
      }
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      e.target.value = '';
    }
  };

  // Tệp đính kèm phải tải qua fetch để mang được header Authorization; thẻ <a href>
  // trần luôn nhận 401. Kèm theo đó, lỗi không còn tứ hiện thành trang lỗi của trình
  // duyệt nữa nên phải tự báo ra.
  const handleDownloadAttachment = async (att) => {
    if (!selectedPatient) return;
    try {
      await apiDownload(`/api/patients/${selectedPatient.id}/attachments/${att.id}/download`);
    } catch (err) {
      console.error('Error downloading attachment:', err);
      showStatus('error', `Không tải được "${att.original_name}": ${err.message}`);
    }
  };

  const handleDeleteAttachment = async (attachmentId) => {
    if (!selectedPatient) return;
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/attachments/${attachmentId}`, { method: 'DELETE' });
      if (res.ok) fetchPatientDetail(selectedPatient.id);
    } catch (err) {
      console.error("Error deleting attachment:", err);
    }
  };

  // --- "Điều trị" tab: "Tạo kế hoạch mới" side panel handlers (creates the underlying visit) ---

  const resetAddVisitForm = () => {
    setNewVisitDate(new Date().toISOString().slice(0, 10));
    setNewVisitDoctor(doctorNamePlain);
    setNewVisitTitle('');
    setNewVisitSymptomInput('');
    setNewVisitSymptoms([]);
    setNewVisitDiagnosis('');
    setNewVisitDiagnosisSecondary('');
    setNewVisitExamFindings('');
    setNewVisitGoals('');
    setNewVisitTreatmentMethod('');
    setNewVisitProtocolDuration('');
    setNewVisitDietRegimen('');
    setNewVisitPrecautions('');
    setNewVisitFollowupPurpose('');
    setNewVisitFollowupDate('');
    setNewVisitTreatmentInstructions('');
    setNewVisitMedications([]);
    setIsAddingVisitMedication(false);
    setVisitMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' });
    setNewVisitNoDrugRecommendations('');
    setNewVisitCareInstructions('');
  };

  const openAddVisitPanel = () => {
    resetAddVisitForm();
    setDiagHandoffPayload(null);
    setIsAddVisitOpen(true);
  };

  // Prefills the "Tạo kế hoạch mới" form from a Diagnosis-Tree handoff payload (see
  // handleUpdateDisease) — used for both the existing-patient path and the new-patient
  // path (chained right after the patient record is created).
  const prefillVisitFromHandoff = (payload) => {
    setNewVisitDate(new Date().toISOString().slice(0, 10));
    setNewVisitDoctor(doctorNamePlain);
    setNewVisitTitle('Khám bệnh theo Sơ đồ chẩn đoán');
    setNewVisitSymptomInput('');
    setNewVisitSymptoms(payload.symptoms);
    setNewVisitDiagnosis(payload.diagnosisPrimary);
    setNewVisitDiagnosisSecondary(payload.diagnosisSecondary);
    setNewVisitExamFindings(payload.exam);
    setNewVisitGoals((payload.goals || []).join('\n'));
    setNewVisitTreatmentMethod(payload.treatmentMethod || '');
    setNewVisitProtocolDuration(payload.protocolDuration || '');
    setNewVisitDietRegimen(payload.dietRegimen || '');
    setNewVisitPrecautions(payload.precautions || '');
    setNewVisitFollowupPurpose('');
    setNewVisitFollowupDate('');
    setNewVisitTreatmentInstructions('');
    setNewVisitMedications(payload.medications || []);
    setIsAddingVisitMedication(false);
    setVisitMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' });
    setNewVisitNoDrugRecommendations(payload.noDrugRecommendations || '');
    setNewVisitCareInstructions(payload.careInstructions || '');
  };

  const handleAddVisitSymptom = () => {
    const val = newVisitSymptomInput.trim();
    if (!val) return;
    setNewVisitSymptoms(prev => [...prev, val]);
    setNewVisitSymptomInput('');
  };

  const handleRemoveVisitSymptom = (idx) => {
    setNewVisitSymptoms(prev => prev.filter((_, i) => i !== idx));
  };

  const handleAddVisitMedication = () => {
    if (!visitMedDraft.name.trim()) return;
    setNewVisitMedications(prev => [...prev, { ...visitMedDraft }]);
    setVisitMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' });
    setIsAddingVisitMedication(false);
  };

  const handleRemoveVisitMedication = (idx) => {
    setNewVisitMedications(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSaveNewVisit = async () => {
    if (!selectedPatient || !newVisitDate) return;
    setIsSavingVisit(true);
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/visits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          visit_date: newVisitDate,
          title: newVisitTitle.trim() || 'Khám bệnh',
          doctor_name: newVisitDoctor.trim() || doctorNamePlain,
          symptoms: newVisitSymptoms.join('\n'),
          diagnosis_primary: newVisitDiagnosis.trim(),
          diagnosis_secondary: newVisitDiagnosisSecondary.trim(),
          exam_findings: newVisitExamFindings.trim(),
          goals: newVisitGoals.split('\n').map(s => s.trim()).filter(Boolean),
          protocol_duration: newVisitProtocolDuration.trim(),
          treatment_method: newVisitTreatmentMethod.trim(),
          diet_regimen: newVisitDietRegimen.trim(),
          precautions: newVisitPrecautions.trim(),
          followup_purpose: newVisitFollowupPurpose.trim(),
          followup_date: newVisitFollowupDate,
          treatment: newVisitTreatmentInstructions.trim(),
          medications: newVisitMedications,
          no_drug_recommendations: newVisitNoDrugRecommendations.trim(),
          care_instructions: newVisitCareInstructions.trim(),
          status: 'in_progress',
          // Structured Top-5 differentials from the Diagnosis-Tree handoff don't have their own
          // inputs in this form (see prefillVisitFromHandoff) — carry them straight through so
          // the Treatment tab can render them.
          ...(diagHandoffPayload ? {
            diagnosis_confidence: diagHandoffPayload.diagnosisConfidence || null,
            differential_diagnoses: diagHandoffPayload.differentialDiagnoses || [],
          } : {}),
        })
      });
      if (res.ok) {
        const created = await res.json();
        showStatus('success', 'Đã thêm lần khám mới.');
        setIsAddVisitOpen(false);
        await fetchPatientDetail(selectedPatient.id);
        if (diagHandoffPayload) {
          setAiReasoningNote(diagHandoffPayload.reasoning || '');
          setDiagHandoffPayload(null);
        }
        setPatientProfileTab('treatment');
        setActiveTreatmentVisitId(created.id);
      } else {
        const data = await res.json();
        throw new Error(data.detail || 'Không thể thêm lần khám.');
      }
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      setIsSavingVisit(false);
    }
  };

  const handleDeleteVisit = async (visitId) => {
    if (!selectedPatient) return;
    if (!confirm('Bạn có chắc chắn muốn xóa lần khám này?')) return;
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/visits/${visitId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        showStatus('success', 'Đã xóa lần khám.');
        if (expandedHistoryVisitId === visitId) setExpandedHistoryVisitId(null);
        if (activeTreatmentVisitId === visitId) setActiveTreatmentVisitId(null);
        await fetchPatientDetail(selectedPatient.id);
      } else {
        throw new Error('Không thể xóa lần khám.');
      }
    } catch (err) {
      showStatus('error', err.message);
    }
  };

  // --- "Điều trị" tab (treatment plan) handlers ---

  const updateTreatmentVisit = async (visitId, patch) => {
    if (!selectedPatient) return false;
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/visits/${visitId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch)
      });
      if (res.ok) {
        await fetchPatientDetail(selectedPatient.id);
        return true;
      }
      throw new Error('Không thể cập nhật kế hoạch điều trị.');
    } catch (err) {
      showStatus('error', err.message);
      return false;
    }
  };

  const handleAiSuggestDiagnosis = async (visit) => {
    if (!visit || !selectedPatient) return;
    if (!visit.symptoms || !visit.symptoms.trim()) {
      showStatus('error', 'Cần nhập triệu chứng trước khi dùng AI gợi ý chẩn đoán.');
      return;
    }
    setAiSuggestLoading(true);
    setAiAgentTrace([]);
    setAiAgentSources([]);
    setAiAgentTraceExpanded(false);
    try {
      const res = await fetch(`/api/patients/${selectedPatient.id}/visits/${visit.id}/ai-diagnosis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symptoms: visit.symptoms })
      });
      if (res.ok) {
        const data = await res.json();
        setAiReasoningNote(data.ai_reasoning || '');
        setAiAgentTrace(data.ai_agent_trace || []);
        setAiAgentSources(data.ai_agent_sources || []);
        await fetchPatientDetail(selectedPatient.id);
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || 'Không thể gợi ý chẩn đoán.');
      }
    } catch (err) {
      showStatus('error', err.message);
    } finally {
      setAiSuggestLoading(false);
    }
  };

  const openDiagnosisEdit = (visit) => {
    setDiagnosisDraft({
      primary: visit.diagnosis_primary || '',
      differentials: visit.diagnosis_secondary || '',
      exam: visit.exam_findings || '',
    });
    setIsEditingDiagnosis(true);
  };

  const handleSaveDiagnosis = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, {
      diagnosis_primary: diagnosisDraft.primary,
      diagnosis_secondary: diagnosisDraft.differentials,
      exam_findings: diagnosisDraft.exam,
    });
    if (ok) setIsEditingDiagnosis(false);
  };

  const openDiagnosisNoteEdit = (visit) => { setDiagnosisNoteDraft(visit.diagnosis_note || ''); setIsEditingDiagnosisNote(true); };
  const handleSaveDiagnosisNote = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, { diagnosis_note: diagnosisNoteDraft });
    if (ok) setIsEditingDiagnosisNote(false);
  };

  const openPlanEdit = (visit) => {
    setPlanDraft({
      goals: (visit.goals || []).join('\n'),
      protocol_duration: visit.protocol_duration || '',
      treatment_method: visit.treatment_method || '',
      diet_regimen: visit.diet_regimen || '',
      precautions: visit.precautions || '',
    });
    setIsEditingPlan(true);
  };
  const handleSavePlan = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, {
      goals: planDraft.goals.split('\n').map(s => s.trim()).filter(Boolean),
      protocol_duration: planDraft.protocol_duration.trim(),
      treatment_method: planDraft.treatment_method.trim(),
      diet_regimen: planDraft.diet_regimen.trim(),
      precautions: planDraft.precautions.trim(),
    });
    if (ok) setIsEditingPlan(false);
  };

  const openNoDrugEdit = (visit) => { setNoDrugDraft(visit.no_drug_recommendations || ''); setIsEditingNoDrug(true); };
  const handleSaveNoDrug = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, { no_drug_recommendations: noDrugDraft });
    if (ok) setIsEditingNoDrug(false);
  };

  const openCareEdit = (visit) => { setCareDraft(visit.care_instructions || ''); setIsEditingCare(true); };
  const handleSaveCare = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, { care_instructions: careDraft });
    if (ok) setIsEditingCare(false);
  };

  const openFollowupEdit = (visit) => { setFollowupDraft({ date: visit.followup_date || '', purpose: visit.followup_purpose || '' }); setIsEditingFollowup(true); };
  const handleSaveFollowup = async (visitId) => {
    const ok = await updateTreatmentVisit(visitId, { followup_date: followupDraft.date, followup_purpose: followupDraft.purpose });
    if (ok) setIsEditingFollowup(false);
  };

  const openAddMedication = () => { setMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' }); setIsAddingMedication(true); };
  const handleSaveMedication = async (visit) => {
    if (!medDraft.name.trim()) return;
    const updated = [...(visit.medications || []), { ...medDraft }];
    const ok = await updateTreatmentVisit(visit.id, { medications: updated });
    if (ok) setIsAddingMedication(false);
  };
  const handleDeleteMedication = async (visit, index) => {
    const updated = visit.medications.filter((_, i) => i !== index);
    await updateTreatmentVisit(visit.id, { medications: updated });
  };

  const handleToggleTreatmentStatus = async (visit) => {
    const next = visit.status === 'completed' ? 'in_progress' : 'completed';
    await updateTreatmentVisit(visit.id, { status: next });
  };

  const handlePrintTreatmentPlan = () => window.print();

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

  const handleNewChat = () => {
    setActiveConversationId(null);
    setDraftWelcome([makeWelcomeMessage()]);
    setActiveSources([]);
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
      setSelectedSourceIndex(0);
    } else {
      setActiveSources([]);
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

  // Groups conversations the way ChatGPT's sidebar does: pinned first, then by recency
  const groupConversationsByDate = (list) => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const sevenDaysAgo = startOfToday - 6 * 86400000;
    const thirtyDaysAgo = startOfToday - 29 * 86400000;

    const groups = { pinned: [], today: [], last7: [], last30: [], older: [] };
    [...list].sort((a, b) => b.updatedAt - a.updatedAt).forEach(c => {
      if (c.pinned) { groups.pinned.push(c); return; }
      if (c.updatedAt >= startOfToday) groups.today.push(c);
      else if (c.updatedAt >= sevenDaysAgo) groups.last7.push(c);
      else if (c.updatedAt >= thirtyDaysAgo) groups.last30.push(c);
      else groups.older.push(c);
    });

    return [
      { key: 'pinned', label: 'Đã ghim', items: groups.pinned },
      { key: 'today', label: 'Hôm nay', items: groups.today },
      { key: 'last7', label: '7 ngày qua', items: groups.last7 },
      { key: 'last30', label: '30 ngày qua', items: groups.last30 },
      { key: 'older', label: 'Cũ hơn', items: groups.older }
    ].filter(g => g.items.length > 0);
  };

  // Chat search (uses LLM) — creates a new conversation on the first message of a draft chat
  const handleSearch = async (searchQuery) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setActiveTab('chat'); // Redirect to chat view when running search

    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    const userMsg = { role: 'user', text: q, time: timeStr };

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
        body: JSON.stringify({ query: q, created_by: doctorName }),
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
          if (sources.length > 0) {
            setActiveSources(sources);
            setSelectedSourceIndex(0);
            setActivePage(sources[0]);
          } else {
            setActiveSources([]);
            setActivePage(null);
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

  /**
   * Đưa lại một lượt tra cứu cũ vào cuộc trò chuyện hiện tại — dùng chính câu
   * trả lời và nguồn đã lưu, không gọi lại LLM (tiết kiệm thời gian & chi phí).
   */
  const handleReuseHistory = (record) => {
    if (!record) return;
    setActiveTab('chat');
    setHistoryOpen(false);

    const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    const userMsg = { role: 'user', text: record.query, time: timeStr };
    const assistantMsg = {
      role: 'assistant',
      text: record.answer || '',
      sources: record.sources || [],
      time: timeStr,
      reused: true,
      reusedAt: record.created_at
    };

    let convId = activeConversationId;
    if (!convId) {
      convId = uid();
      setConversations(prev => [{
        id: convId,
        title: createConversationTitle(record.query),
        messages: [userMsg, assistantMsg],
        pinned: false,
        createdAt: Date.now(),
        updatedAt: Date.now()
      }, ...prev]);
      setActiveConversationId(convId);
    } else {
      appendMessageToConversation(convId, userMsg);
      appendMessageToConversation(convId, assistantMsg);
    }

    setQuery('');
    if (record.sources?.length > 0) {
      setActiveSources(record.sources);
      setSelectedSourceIndex(0);
      setActivePage(record.sources[0]);
    }
    showStatus('success', 'Đã dùng lại kết quả tra cứu đã lưu.');
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
    text += `Được tạo bởi mô hình Deepseek • Cập nhật: ${drugReport.created_at || 'Hôm nay'}\n\n`;

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

    text += `\n---\n*Lưu ý: Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán và chỉ định của bác sĩ.*`;

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

  const formatLibraryDate = (epochSeconds) => {
    if (!epochSeconds) return '';
    return new Date(epochSeconds * 1000).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const handleOpenLibraryPreview = async (docName, pageNum = 1) => {
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docName)}/pages/${pageNum}`);
      if (res.ok) {
        const data = await res.json();
        setLibraryPreview(data);
      } else {
        const errData = await res.json();
        showStatus('error', errData.detail || "Không thể đọc nội dung trang.");
      }
    } catch (err) {
      showStatus('error', "Lỗi kết nối khi tải trang tài liệu.");
    }
  };

  const handleLibraryPrevPage = () => {
    if (!libraryPreview) return;
    const prevPage = libraryPreview.page_num - 1;
    if (prevPage < 1) return;
    handleOpenLibraryPreview(libraryPreview.doc_name, prevPage);
  };

  const handleLibraryNextPage = () => {
    if (!libraryPreview) return;
    const nextPage = libraryPreview.page_num + 1;
    const docInfo = documents.find(d => d.doc_name === libraryPreview.doc_name);
    const maxPage = docInfo ? docInfo.page_count : 1;
    if (nextPage > maxPage) return;
    handleOpenLibraryPreview(libraryPreview.doc_name, nextPage);
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
    try {
      const res = await fetch('/api/diagnosis-tree/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ description: patientDesc })
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Tạo cây chẩn đoán thất bại.");
      }
      const data = await res.json();
      setDiagnosisTree(data);
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
              <Stethoscope size={15} style={{ color: status ? '#2563eb' : 'var(--primary)', flexShrink: 0 }} />
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
              <Stethoscope size={15} style={{ color: (status || '').trim() ? '#2563eb' : 'var(--primary)', flexShrink: 0 }} />
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
        body: JSON.stringify({ confirmed_symptoms: confirmed, excluded_symptoms: excluded })
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
        body: JSON.stringify({ confirmed_symptoms: confirmed, excluded_symptoms: excluded, exam_notes: examNotes })
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

  // --- "Bệnh nhân" linking section (Diagnosis Tree tab) ---

  const handleDiagPatientSearchChange = async (value) => {
    setDiagPatientQuery(value);
    setDiagPatientSearchOpen(true);
    setDiagSelectedPatient(null);
    if (!value.trim()) { setDiagPatientResults([]); return; }
    try {
      const res = await fetch(`/api/patients?search=${encodeURIComponent(value)}`);
      if (res.ok) setDiagPatientResults((await res.json()) || []);
    } catch (err) {
      console.error("Error searching patients:", err);
    }
  };

  const handleSelectDiagPatient = (pat) => {
    setDiagSelectedPatient(pat);
    setDiagPatientQuery(pat.name);
    setDiagPatientSearchOpen(false);
    setDiagPatientResults([]);
  };

  const handleToggleDiagnosisSelected = (idx) => {
    setSelectedDiagnosisIds(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // "Cập nhật bệnh" — hands the diagnoses the doctor picked off to the Patients tab: fetches an
  // AI medication/care suggestion for just those, then opens "+ Thêm lần khám" pre-filled for an
  // existing patient, or "+ Thêm bệnh nhân" (then chains into "+ Thêm lần khám" once saved) for a new one.
  const handleUpdateDisease = async () => {
    if (selectedDiagnosisIds.size === 0) return;
    const { confirmed } = collectSymptoms(treeRoot, nodeStatusMap);
    const chosen = finalDiagnoses.filter((_, idx) => selectedDiagnosisIds.has(idx));
    const ranked = [...chosen].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    const [top, ...rest] = ranked;
    const formatDiag = (d) => (d.icd10 ? `${d.disease_name} (${d.icd10})` : d.disease_name);

    setIsPreparingHandoff(true);
    let treatment = {
      medications: [], no_drug_recommendations: '', care_instructions: '',
      goals: [], protocol_duration: '', treatment_method: '', diet_regimen: '', precautions: '',
    };
    try {
      const res = await fetch('/api/diagnosis-tree/treatment', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Deepseek-Key': apiKey || ''
        },
        body: JSON.stringify({ diagnoses: ranked, exam_notes: examNotes })
      });
      if (res.ok) treatment = await res.json();
    } catch (err) {
      console.error("Error generating treatment suggestion:", err);
    } finally {
      setIsPreparingHandoff(false);
    }

    // Up to 5 differentials (everything but the top pick) with their ICD-10/confidence/reasoning
    // preserved — feeds the "Chẩn đoán phân biệt (Top 5)" table on the Treatment tab instead of
    // collapsing to a flat string like diagnosisSecondary (kept below for the plain-text views).
    const differentialDiagnoses = rest.slice(0, 5).map(d => ({
      name: d.disease_name, icd10: d.icd10 || '', confidence: d.confidence || 0,
      note: d.red_flags || '', reasoning: d.reasoning || '',
    }));

    const payload = {
      symptoms: confirmed,
      diagnosisPrimary: formatDiag(top),
      diagnosisSecondary: rest.map(formatDiag).join('\n'),
      diagnosisConfidence: top.confidence || 0,
      differentialDiagnoses,
      exam: examNotes,
      reasoning: top.reasoning || '',
      medications: treatment.medications || [],
      noDrugRecommendations: treatment.no_drug_recommendations || '',
      careInstructions: treatment.care_instructions || '',
      goals: treatment.goals || [],
      protocolDuration: treatment.protocol_duration || '',
      treatmentMethod: treatment.treatment_method || '',
      dietRegimen: treatment.diet_regimen || '',
      precautions: treatment.precautions || '',
    };

    setActiveTab('patients');

    if (diagSelectedPatient) {
      setSelectedPatientId(diagSelectedPatient.id);
      setDiagHandoffPayload(payload);
      prefillVisitFromHandoff(payload);
      setIsAddVisitOpen(true);
    } else {
      openAddPatientModal(payload);
    }
  };

  // Turns bare "[1]" citation markers from the LLM into a fake markdown link (#cite-1) so
  // react-markdown parses them as an <a>, which the custom `a` renderer below swaps for a citation badge.
  const preprocessCitations = (text) => (text || '').replace(/\[(\d+)\]/g, (_, num) => `[${num}](#cite-${num})`);

  // Nhãn hiển thị của một nguồn. Backend trả về doc_title (tên sách) và
  // citation ("Dược thư QGVN 2022, Q.1 — tr. 297"); các kết quả cũ trong lịch
  // sử tra cứu chỉ có doc_name nên vẫn phải có đường lui.
  const sourceTitle = (src) => src?.doc_title || src?.doc_name || '';
  const sourceCitation = (src) =>
    src?.citation || `${src?.doc_name || ''} — tr. ${src?.page_num ?? '?'}`;

  const sourcePublisher = (src) => {
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
            if (source) {
              setSelectedSourceIndex(num - 1);
              handleOpenPageReader(source.doc_name, source.page_num, source);
            }
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


  const showSourcesToggle = activeTab === 'chat' || activeTab === 'medicine';

  const currentTreatmentVisit = selectedPatient
    ? (selectedPatient.visits.find(v => v.id === activeTreatmentVisitId) || selectedPatient.visits[0] || null)
    : null;

  const currentNote = selectedPatient
    ? (selectedPatient.notes || []).find(n => n.id === activeNoteId) || null
    : null;

  // Defaults the "Ghi chú" tab to the most recent note whenever the patient (or its notes)
  // change, opening straight into the full form if that note is still a draft — a draft has
  // no view mode. Skipped mid-creation of a brand-new, not-yet-saved note (activeNoteId null
  // with the form already open) so we don't silently discard unsaved input.
  useEffect(() => {
    if (!selectedPatient) return;
    if (isNoteFormOpen && !activeNoteId) return;
    const notes = selectedPatient.notes || [];
    if (activeNoteId && notes.some(n => n.id === activeNoteId)) return;
    const first = notes[0] || null;
    setActiveNoteId(first ? first.id : null);
    if (first && first.status === 'draft') {
      setNoteFormDraft(noteToDraft(first));
      setIsNoteFormOpen(true);
    } else {
      setIsNoteFormOpen(false);
    }
  }, [selectedPatient?.id, selectedPatient?.notes]); // eslint-disable-line react-hooks/exhaustive-deps

  // Renders one read-only field on a finalized note's view mode — editing is bulk-only now
  // (the "Sửa" button on the note reopens the full form), so this has no per-field controls.
  const renderNoteReadField = (note, fieldKey, label) => (
    <div className="pp-tp-note-box" key={fieldKey}>
      <div className="pp-tp-note-box-head">
        <span className="pp-tp-note-label">{label}</span>
      </div>
      <p className="pp-tp-note-text">{note[fieldKey] || 'Chưa ghi nhận.'}</p>
    </div>
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
        <div className="sidebar-brand">
          <div className="sidebar-brand-left">
            <div className="brand-logo">
              <Pill size={17} className="logo-icon" />
            </div>
            {!isSidebarCollapsed && (
              <div className="brand-wordmark">
                <strong>Trợ lý Fil</strong>
                <span>Beta</span>
              </div>
            )}
          </div>
          <button
            className="btn-sidebar-collapse"
            onClick={() => setIsSidebarCollapsed(v => !v)}
            title={isSidebarCollapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
          >
            {isSidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <button
          className={`btn-new-chat ${activeTab === 'chat' && !activeConversationId ? 'active' : ''}`}
          onClick={handleNewChat}
          title="Cuộc trò chuyện mới"
        >
          <Plus size={16} />
          {!isSidebarCollapsed && <span>Cuộc trò chuyện mới</span>}
        </button>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeTab === 'medicine' ? 'active' : ''}`}
            onClick={() => setActiveTab('medicine')}
            title="Tra cứu Thuốc"
          >
            <Pill size={19} />
            <span>Thuốc</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'library' ? 'active' : ''}`}
            onClick={() => setActiveTab('library')}
            title="Thư viện tài liệu"
          >
            <Library size={19} />
            <span>Thư viện</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'compare' ? 'active' : ''}`}
            onClick={() => setActiveTab('compare')}
            title="Đối chiếu nhiều nguồn tài liệu"
          >
            <GitCompareArrows size={19} />
            <span>Đối chiếu</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'patients' ? 'active' : ''}`}
            onClick={() => setActiveTab('patients')}
            title="Bệnh nhân"
          >
            <Users size={19} />
            <span>Bệnh nhân</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'reminders' ? 'active' : ''}`}
            onClick={() => setActiveTab('reminders')}
            title="Nhắc lịch tái khám & theo dõi"
          >
            <BellRing size={19} />
            <span>Nhắc lịch</span>
            {visibleNotifications.length > 0 && (
              <span className="nav-item-badge">{visibleNotifications.length}</span>
            )}
          </button>

          <button
            className={`nav-item ${activeTab === 'stats' ? 'active' : ''}`}
            onClick={() => setActiveTab('stats')}
            title="Thống kê phòng khám"
          >
            <BarChart3 size={19} />
            <span>Thống kê</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'diagnosisTree' ? 'active' : ''}`}
            onClick={() => setActiveTab('diagnosisTree')}
            title="Sơ đồ chẩn đoán"
          >
            <GitBranch size={19} />
            <span>Chẩn đoán</span>
          </button>

          <button
            className={`nav-item ${activeTab === 'about' ? 'active' : ''}`}
            onClick={() => setActiveTab('about')}
            title="Giới thiệu"
          >
            <Info size={19} />
            <span>Giới thiệu</span>
          </button>
        </nav>

        <div className="sidebar-divider" />

        {!isSidebarCollapsed && (
          <div className="sidebar-history-section">
            {conversations.length === 0 ? (
              <div className="sidebar-history-empty">Chưa có cuộc trò chuyện nào.</div>
            ) : (
              <div className="sidebar-history-list">
                {groupConversationsByDate(conversations.filter(c => !c.archived)).map(group => (
                  <div className="conv-group" key={group.key}>
                    <div className="conv-group-label">{group.label}</div>
                    <AnimatePresence initial={false}>
                      {group.items.map(conv => (
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
                          {conv.pinned && <Pin size={11} className="conv-item-pin-icon" />}
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
                      ))}
                    </AnimatePresence>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="sidebar-footer">
          <ExportPdfDialog
            open={exportPdfOpen}
            onOpenChange={setExportPdfOpen}
            patient={selectedPatient}
          />

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

      {/* Lịch sử tra cứu — duyệt lại và dùng lại kết quả cũ */}
      <SearchHistoryDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        onReuse={handleReuseHistory}
        onNotify={showStatus}
      />

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
                    <Dialog.Title className="lightbox-title">{libraryPreview.doc_name}</Dialog.Title>
                  </div>
                  <div className="lightbox-header-actions">
                    <button className="icon-btn-action" onClick={() => handleDownloadDocument(libraryPreview.doc_name)} title="Tải xuống">
                      <Download size={16} />
                    </button>
                    <Dialog.Close asChild>
                      <button className="icon-btn-action" title="Đóng"><X size={16} /></button>
                    </Dialog.Close>
                  </div>
                </div>
                <Dialog.Description className="sr-only">
                  Đọc, tô sáng và ghi chú trên tài liệu {libraryPreview.doc_name}
                </Dialog.Description>
                <DocumentAnnotator
                  docName={libraryPreview.doc_name}
                  pageNum={libraryPreview.page_num}
                  pageText={libraryPreview.text}
                  doctorName={doctorName}
                  onNotify={showStatus}
                />
                <div className="lightbox-footer reader-footer-pagination">
                  <button onClick={handleLibraryPrevPage} disabled={libraryPreview.page_num <= 1}>
                    <ChevronLeft size={15} />
                  </button>
                  <span className="pagination-text">
                    Trang {libraryPreview.page_num} / {documents.find(d => d.doc_name === libraryPreview.doc_name)?.page_count || '?'}
                  </span>
                  <button onClick={handleLibraryNextPage}>
                    <ChevronRight size={15} />
                  </button>
                </div>
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

                  <div className="factcheck-full-text-title">
                    <BookOpen size={16} />
                    <span>Toàn văn tài liệu tham khảo ({selectedFactCheckDoc.page_num || 'Trang'})</span>
                  </div>
                  <div className="factcheck-full-text-body">
                    {renderSimpleMarkdown(selectedFactCheckDoc.text || selectedFactCheckDoc.snippet || 'Tài liệu hướng dẫn sử dụng thuốc và dược thư chuyên khảo.')}
                  </div>
                </div>

                <div className="factcheck-footer">
                  <span className="factcheck-footer-note">
                    <CheckCircle2 size={15} className="text-accent" />
                    Dữ liệu được đối chiếu trực tiếp từ kho y văn chính thống.
                  </span>
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
                  Tất cả tài liệu tham khảo ({(drugReport.sources || []).length})
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
                {(drugReport.sources || [])
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
              <h1 className="header-brand-title">Trợ lý FII</h1>
              <span className="badge-beta">BETA</span>
            </div>
          </div>
          <div className="header-actions">
            {/* Notification Bell */}
            {notifyEnabled && (
              <DropdownMenu.Root onOpenChange={(open) => { if (open) fetchNotifications(); }}>
                <DropdownMenu.Trigger asChild>
                  <button className="btn-header-bell" title="Thông báo">
                    <Bell size={18} />
                    {visibleNotifications.length > 0 && (
                      <span className="bell-badge">{visibleNotifications.length}</span>
                    )}
                  </button>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content className="notif-dropdown-content" align="end" sideOffset={8}>
                    <div className="notif-dropdown-header">Thông báo</div>
                    {notifLoading ? (
                      <div className="notif-dropdown-empty"><Loader2 className="animate-spin" size={16} /> Đang tải...</div>
                    ) : visibleNotifications.length === 0 ? (
                      <div className="notif-dropdown-empty">Không có nhắc lịch nào cần xử lý.</div>
                    ) : (
                      <div className="notif-dropdown-list">
                        {visibleNotifications.map((n) => (
                          <div
                            key={n.reminder_id || n.visit_id}
                            className={`notif-item ${n.overdue ? 'notif-item-overdue' : ''}`}
                            onClick={() => handleNotificationClick(n)}
                          >
                            <div className={`notif-item-dot ${n.overdue ? 'overdue' : ''}`} />
                            <div className="notif-item-body">
                              <div className="notif-item-title">
                                {n.patient_name}
                                {n.kind_label && n.kind !== 'followup' && (
                                  <span className="notif-item-kind">{n.kind_label}</span>
                                )}
                              </div>
                              <div className="notif-item-desc">
                                {n.followup_purpose || n.title || 'Tái khám'} • {formatDateVN(n.followup_date)}
                              </div>
                              <div className={`notif-item-due ${n.overdue ? 'overdue' : ''}`}>
                                {formatFollowupDueLabel(n.days_diff)}
                                {n.snoozed && <span className="notif-item-snoozed">đã hoãn</span>}
                              </div>
                            </div>
                            <div className="notif-item-actions">
                              {!permissions.isReadOnly && n.reminder_id && (
                                <>
                                  <button
                                    className="notif-item-act"
                                    title="Đánh dấu đã tái khám"
                                    onClick={(e) => { e.stopPropagation(); actOnNotification(n, 'complete'); }}
                                  >
                                    <Check size={13} />
                                  </button>
                                  <button
                                    className="notif-item-act"
                                    title="Hoãn 3 ngày"
                                    onClick={(e) => { e.stopPropagation(); actOnNotification(n, 'snooze', { days: 3 }); }}
                                  >
                                    <Clock size={13} />
                                  </button>
                                </>
                              )}
                              <button
                                className="notif-item-dismiss"
                                title="Ẩn khỏi danh sách này"
                                onClick={(e) => { e.stopPropagation(); dismissNotification(n.visit_id); }}
                              >
                                <X size={13} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <button
                      type="button"
                      className="notif-dropdown-footer"
                      onClick={() => setActiveTab('reminders')}
                    >
                      Mở trang nhắc lịch <ChevronRight size={13} />
                    </button>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            )}

            {/* Dark Mode Toggle */}
            <button
              className="btn-theme-toggle"
              onClick={toggleTheme}
              title={isDarkMode ? "Chuyển sang Giao diện Sáng" : "Chuyển sang Giao diện Tối"}
            >
              {isDarkMode ? <Sun size={19} /> : <Moon size={19} />}
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
                  {/* Bong bong tra loi da ton tai va tu chay chu, nen khong con
                      mot hang cho rieng nua — hai cai cung luc la hai vong xoay.
                      Cho lai day dung mot thu: duong ra. */}
                  {loading && (
                    <div className="chat-cancel-row">
                      <button
                        type="button"
                        className="chat-cancel-btn"
                        onClick={handleCancelSearch}
                      >
                        <X size={14} />
                        Dừng tra cứu
                      </button>
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
                  <SimilarQuestions
                    query={query}
                    disabled={loading}
                    onReuse={handleReuseHistory}
                  />
                  <div className="input-row">
                    <textarea
                      ref={chatInputRef}
                      className="input-textarea"
                      placeholder={isRecording === 'chat' ? "Đang nghe... hãy nói câu hỏi của bạn" : "Đặt câu hỏi lâm sàng dựa trên y văn đã chỉ mục..."}
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSearch();
                        }
                      }}
                    />
                    <div className="input-actions-right">
                      {settings.voiceInputEnabled && (
                        <button
                          type="button"
                          className={`btn-mic ${isRecording === 'chat' ? 'recording' : ''}`}
                          onClick={() => handleToggleMic('chat', setQuery, () => handleSearch())}
                          title={!micSupported ? "Trình duyệt không hỗ trợ ghi âm" : (isRecording === 'chat' ? "Dừng ghi âm" : "Ghi âm giọng nói")}
                        >
                          {isRecording === 'chat' ? <Square size={14} /> : <Mic size={18} />}
                        </button>
                      )}
                      <button type="submit" className="btn-send" disabled={loading || !query.trim()}>
                        <Send size={16} />
                      </button>
                    </div>
                  </div>
                  <div className="input-footer">
                    <CheckCircle2 size={14} className="checkmark-icon" />
                    <span>Nguồn: Đối chiếu sách hướng dẫn điều trị Bộ Y Tế & GINA/ESC</span>
                    <button
                      type="button"
                      className="btn-history-link"
                      onClick={() => setHistoryOpen(true)}
                      title="Xem lại các câu hỏi đã tra cứu trước đây"
                    >
                      <History size={13} />
                      Lịch sử tra cứu
                    </button>
                  </div>
                </form>
              </div>

              {/* Right Column: References & Reader */}
              {showSourcesPanel && (
                <div className="reference-panel">
                  {/* Reference list (NotebookLM-style Sources rail) */}
                  <div className="citation-list-card">
                    <div className="card-header">
                      <div className="card-header-left">
                        <BookOpen size={18} className="header-icon-blue" />
                        <h2>Nguồn ({activeSources.length})</h2>
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
                        <h3 className="reader-doc-title" title={sourceCitation(activePage)}>
                          {sourceTitle(activePage)} — Trang {activePage.page_num}
                        </h3>
                        <div className="reader-header-actions">
                          {/* Với sách scan, bản OCR chính là chỗ có thể sai. Bác sĩ
                              fact-check được chỉ khi nhìn thấy trang in thật. */}
                          <button
                            className={`icon-btn-action ${readerShowScan ? 'active' : ''}`}
                            onClick={() => setReaderShowScan(v => !v)}
                            title={readerShowScan ? 'Xem văn bản OCR' : 'Xem ảnh trang gốc để đối chiếu'}
                          >
                            {readerShowScan ? <FileText size={16} /> : <ScanLine size={16} />}
                          </button>
                          <button className="icon-btn-action" title="Mở rộng"><ExternalLink size={16} /></button>
                          <button className="icon-btn-action" onClick={() => setActivePage(null)} title="Đóng"><X size={16} /></button>
                        </div>
                      </div>
                      <div className="reader-content-body">
                        {readerShowScan ? (
                          <AuthedImage
                            className="reader-scan-image"
                            url={`/api/documents/${encodeURIComponent(activePage.doc_name)}/pages/${activePage.page_num}/image?dpi=150`}
                            alt={`Ảnh scan ${sourceCitation(activePage)}`}
                          />
                        ) : (
                          renderSimpleMarkdown(activePage.text)
                        )}
                      </div>
                      <div className="reader-footer-pagination">
                        <button onClick={handlePrevPage} disabled={activePage.page_num <= readerMinPage(activePage.doc_name)}>
                          <ChevronLeft size={16} />
                        </button>
                        <span className="pagination-text">
                          Trang {activePage.page_num} / {readerMaxPage(activePage.doc_name) || '?'}
                        </span>
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
          {activeTab === 'medicine' && (
            <div className="drug-lookup-view">
              {/* Top Title & Subtitle */}
              <div className="drug-hero-header">
                <h1 className="drug-hero-title">Tra cứu thuốc</h1>
                <p className="drug-hero-desc">
                  AI hỗ trợ thông tin thuốc dựa trên dữ liệu y khoa đáng tin cậy.
                </p>
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
              <div className="drug-main-grid">
                {/* LEFT COLUMN: Báo cáo AI */}
                <div className="drug-report-card">
                  <div className="drug-report-card-header">
                    <div className="drug-report-meta-left">
                      <h2 className="drug-report-title">Báo cáo AI</h2>
                      <p className="drug-report-meta-text">
                        Được tạo bởi mô hình {drugReport.model_used || 'Deepseek'} • Cập nhật: {drugReport.created_at || '29/08/2026 14:30'}
                      </p>
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
                          <h4>Đang tổng hợp thông tin y khoa từ DeepSeek & Dược thư...</h4>
                          <p>Phân tích chỉ định, liều dùng, tương tác thuốc và tài liệu tham khảo</p>
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
                                Độ tin cậy: {sec.confidence || drugReport.confidence_overall || 'Cao'}
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
                      <h3 className="drug-resources-title">Tài liệu nguồn (Resources)</h3>
                      <p className="drug-resources-subtitle">
                        Các tài liệu tham khảo được AI sử dụng để tạo báo cáo. Bạn nên kiểm chứng thông tin từ nguồn gốc.
                      </p>
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
                            <span className="drug-resource-meta">{src.file_size || 'PDF • 2.1 MB'}</span>
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
                      <span>Xem tất cả tài liệu ({(drugReport.sources || []).length || 12})</span>
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {/* Card 2: Tóm tắt nhanh */}
                  <div className="drug-quick-summary-card">
                    <h3 className="drug-quick-summary-title">Tóm tắt nhanh</h3>
                    <div className="drug-quick-summary-list">
                      {(drugReport.quick_summary || [
                        { type: 'success', text: 'Giảm đau, hạ sốt hiệu quả' },
                        { type: 'success', text: 'An toàn nếu dùng đúng liều' },
                        { type: 'warning', text: 'Nguy cơ độc gan khi quá liều' },
                        { type: 'danger', text: 'Tránh dùng chung với rượu' }
                      ]).map((item, idx) => {
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

                  {/* Footer Disclaimer */}
                  <div className="drug-disclaimer-text">
                    Lưu ý: Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán và chỉ định của bác sĩ.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Thư viện (document library manager, formerly the "Tra cứu" manage sub-tab) */}
          {activeTab === 'library' && (() => {
            const filteredLibraryDocs = documents
              .filter(d => d.doc_name.toLowerCase().includes(librarySearch.trim().toLowerCase()))
              .sort((a, b) => {
                if (librarySortBy === 'name') return a.doc_name.localeCompare(b.doc_name);
                if (librarySortBy === 'pages') return (b.page_count || 0) - (a.page_count || 0);
                if (librarySortBy === 'oldest') return (a.uploaded_at || 0) - (b.uploaded_at || 0);
                return (b.uploaded_at || 0) - (a.uploaded_at || 0); // newest (default)
              });

            const docMenu = (doc) => (
              <DropdownMenu.Root>
                <DropdownMenu.Trigger asChild>
                  <button
                    className="card-menu-btn"
                    onClick={(e) => e.stopPropagation()}
                    title="Tùy chọn tài liệu"
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
                    <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleOpenLibraryPreview(doc.doc_name, 1)}>
                      <Eye size={14} />
                      Xem trước
                    </DropdownMenu.Item>
                    <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleDownloadDocument(doc.doc_name)}>
                      <Download size={14} />
                      Tải xuống
                    </DropdownMenu.Item>
                    <DropdownMenu.Separator className="dropdown-menu-separator" />
                    <DropdownMenu.Item className="dropdown-menu-item danger" onSelect={() => setDeleteDocTarget(doc.doc_name)}>
                      <Trash2 size={14} />
                      Xóa
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            );

            return (
              <div className="docs-tab-view animate-fade-in">
                <div className="view-header">
                  <h2>Thư viện</h2>
                  <p>Toàn bộ tài liệu PDF đã tải lên và lập chỉ mục để tra cứu và trò chuyện, trình bày như ChatGPT Library.</p>
                </div>

                <div className="lib-toolbar">
                  <div className="lib-search-wrap">
                    <Search size={14} className="lib-search-icon" />
                    <input
                      type="text"
                      className="lib-search-input"
                      placeholder="Tìm tài liệu..."
                      value={librarySearch}
                      onChange={(e) => setLibrarySearch(e.target.value)}
                    />
                  </div>

                  <select
                    className="lib-sort-select"
                    value={librarySortBy}
                    onChange={(e) => setLibrarySortBy(e.target.value)}
                    title="Sắp xếp"
                  >
                    <option value="newest">Mới nhất</option>
                    <option value="oldest">Cũ nhất</option>
                    <option value="name">Tên A-Z</option>
                    <option value="pages">Nhiều trang nhất</option>
                  </select>

                  <div className="lib-view-toggle">
                    <button
                      className={libraryViewMode === 'grid' ? 'active' : ''}
                      onClick={() => setLibraryViewMode('grid')}
                      title="Xem dạng lưới"
                    >
                      <LayoutGrid size={15} />
                    </button>
                    <button
                      className={libraryViewMode === 'list' ? 'active' : ''}
                      onClick={() => setLibraryViewMode('list')}
                      title="Xem dạng danh sách"
                    >
                      <List size={15} />
                    </button>
                  </div>

                  <button
                    type="button"
                    className="btn-lib-upload"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                  >
                    {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                    {uploading ? "Đang tải lên..." : "Tải tệp lên"}
                  </button>
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".pdf"
                    style={{ display: 'none' }}
                    disabled={uploading}
                  />
                </div>

                {documents.length === 0 ? (
                  <div className="lib-empty">
                    <div className="lib-empty-icon"><FileText size={26} /></div>
                    <h4>Chưa có tài liệu nào</h4>
                    <p>Tải lên tệp PDF đầu tiên để hệ thống lập chỉ mục và có thể tra cứu, trò chuyện dựa trên nội dung tài liệu.</p>
                    <button type="button" className="btn-lib-upload" onClick={() => fileInputRef.current?.click()} style={{ marginLeft: 0 }}>
                      <Upload size={15} />
                      Tải tệp lên
                    </button>
                  </div>
                ) : filteredLibraryDocs.length === 0 ? (
                  <div className="lib-empty">
                    <div className="lib-empty-icon"><Search size={24} /></div>
                    <h4>Không tìm thấy tài liệu</h4>
                    <p>Không có tài liệu nào khớp với từ khóa "{librarySearch}".</p>
                  </div>
                ) : libraryViewMode === 'grid' ? (
                  <div className="lib-grid">
                    {filteredLibraryDocs.map((doc) => (
                      <div
                        key={doc.doc_name}
                        className="lib-card"
                        onClick={() => handleOpenLibraryPreview(doc.doc_name, 1)}
                      >
                        {docMenu(doc)}
                        <div className="lib-card-thumb">
                          <div className="lib-card-thumb-icon"><FileText size={22} /></div>
                        </div>
                        <div className="lib-card-body">
                          <div className="lib-card-title" title={doc.doc_name}>{doc.doc_name}</div>
                          <div className="lib-card-meta">
                            {doc.page_count} trang • {doc.chunk_count} đoạn
                            {doc.uploaded_at ? ` • ${formatLibraryDate(doc.uploaded_at)}` : ''}
                          </div>
                          {highlightCounts[doc.doc_name] > 0 && (
                            <span className="lib-highlight-badge" title="Số đoạn bạn đã tô sáng trong tài liệu này">
                              <PencilLine size={11} />
                              {highlightCounts[doc.doc_name]} ghi chú
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="lib-list">
                    {filteredLibraryDocs.map((doc) => (
                      <div
                        key={doc.doc_name}
                        className="lib-row"
                        onClick={() => handleOpenLibraryPreview(doc.doc_name, 1)}
                      >
                        <div className="lib-row-icon"><FileText size={17} /></div>
                        <div className="lib-row-body">
                          <div className="lib-row-title" title={doc.doc_name}>{doc.doc_name}</div>
                          <div className="lib-row-meta">
                            {doc.page_count} trang • {doc.chunk_count} đoạn
                            {doc.uploaded_at ? ` • ${formatLibraryDate(doc.uploaded_at)}` : ''}
                            {highlightCounts[doc.doc_name] > 0 && ` • ${highlightCounts[doc.doc_name]} ghi chú`}
                          </div>
                        </div>
                        {docMenu(doc)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* TAB: Đối chiếu nguồn — cùng một câu hỏi, nhiều tài liệu */}
          {activeTab === 'compare' && (
            <CompareView
              documents={documents}
              apiKey={apiKey}
              onOpenSource={(docName, pageNum) => handleOpenLibraryPreview(docName, pageNum)}
              onNotify={showStatus}
            />
          )}

          {/* TAB 4: Hồ sơ bệnh nhân (Patient Profile) */}
          {activeTab === 'patients' && (
            <div className="pp-view animate-fade-in">
              <div className="pp-topbar">
                <h1 className="pp-title">Hồ sơ bệnh nhân</h1>

                <div className="pp-search-wrap">
                  <Search size={16} className="pp-search-icon" />
                  <input
                    type="text"
                    className="pp-search-input"
                    placeholder="Tìm kiếm bệnh nhân..."
                    value={patientSearchQuery}
                    onChange={(e) => handlePatientSearchChange(e.target.value)}
                    onFocus={() => setPatientSearchOpen(true)}
                    onBlur={() => setTimeout(() => setPatientSearchOpen(false), 150)}
                  />
                  <kbd className="pp-search-kbd">Ctrl K</kbd>

                  {patientSearchOpen && patientSearchQuery.trim() && (
                    <div className="pp-search-dropdown">
                      {patientSearchResults.length === 0 ? (
                        <div className="pp-search-empty">Không tìm thấy bệnh nhân phù hợp.</div>
                      ) : (
                        patientSearchResults.map((pat) => (
                          <div
                            key={pat.id}
                            className="pp-search-result"
                            onMouseDown={() => handleSelectSearchedPatient(pat.id)}
                          >
                            <div className="pp-search-result-avatar"><UserRound size={14} /></div>
                            <div>
                              <div className="pp-search-result-name">{pat.name}</div>
                              <div className="pp-search-result-meta">{pat.code}{pat.age != null ? ` • ${pat.age} tuổi` : ''}</div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

                <div className="pp-topbar-actions">
                  {selectedPatient && (
                    <button
                      className="pp-btn-outline"
                      onClick={() => setExportPdfOpen(true)}
                      title="Xuất bệnh án, phiếu khám hoặc giấy chuyển tuyến ra PDF"
                    >
                      <Printer size={15} /> Xuất PDF
                    </button>
                  )}
                  {!permissions.isReadOnly && (
                    <button className="pp-btn-add" onClick={() => openAddPatientModal()}>
                      <Plus size={16} /> Thêm bệnh nhân
                    </button>
                  )}
                </div>
              </div>

              {patients.length === 0 ? (
                <div className="pp-empty-state">
                  <div className="pp-empty-icon"><Users size={28} /></div>
                  <h3>Chưa có hồ sơ bệnh nhân nào</h3>
                  <p>
                    {permissions.isReadOnly
                      ? 'Chưa bác sĩ nào trong phòng khám tạo hồ sơ bệnh nhân.'
                      : permissions.seesAllPatients
                        ? 'Bắt đầu bằng cách thêm bệnh nhân đầu tiên vào hệ thống.'
                        : 'Bạn chưa phụ trách hồ sơ nào. Thêm bệnh nhân mới, hoặc nhờ quản trị bàn giao hồ sơ cho bạn.'}
                  </p>
                  {!permissions.isReadOnly && (
                    <button className="pp-btn-add" onClick={() => openAddPatientModal()}><Plus size={16} /> Thêm bệnh nhân</button>
                  )}
                </div>
              ) : patientDetailLoading || !selectedPatient ? (
                <div className="pp-loading-state"><Loader2 className="animate-spin" size={24} /><span>Đang tải hồ sơ bệnh nhân...</span></div>
              ) : (
                <>
                  <div className="pp-body">
                    <div className="pp-main">
                      {/* Patient header card */}
                      <div className="pp-header-card">
                        <div className="pp-identity">
                          <div className="pp-avatar"><UserRound size={30} /></div>
                          <div className="pp-identity-info">
                            <div className="pp-name-row">
                              <h2>{selectedPatient.name}</h2>
                              <span className={`pp-gender-symbol ${selectedPatient.gender === 'Nữ' ? 'female' : 'male'}`}>
                                {selectedPatient.gender === 'Nữ' ? '♀' : '♂'}
                              </span>
                            </div>
                            <div className="pp-id-badge">ID: {selectedPatient.code}</div>
                            <div className="pp-owner-row">
                              <Stethoscope size={12} />
                              {selectedPatient.owner_name
                                ? <>Phụ trách: <strong>{selectedPatient.owner_name}</strong></>
                                : <span className="pp-owner-none">Chưa có bác sĩ phụ trách</span>}
                              {permissions.isReadOnly && (
                                <span className="pp-readonly-chip"><Lock size={11} /> chỉ xem</span>
                              )}
                            </div>
                            <div className="pp-meta-row">
                              <span><Users size={13} /> {selectedPatient.gender || '--'}</span>
                            </div>
                            {selectedPatient.phone && <div className="pp-contact-row"><Phone size={13} /> {selectedPatient.phone}</div>}
                            {selectedPatient.address && <div className="pp-contact-row"><MapPin size={13} /> {selectedPatient.address}</div>}
                          </div>
                        </div>

                        <div className="pp-stats-grid">
                          <div className="pp-stat"><span className="pp-stat-label">Nhóm máu</span><span className="pp-stat-value pp-blood">{selectedPatient.blood_type || '--'}</span></div>
                          <div className="pp-stat"><span className="pp-stat-label">Cân nặng</span><span className="pp-stat-value">{selectedPatient.weight_kg ? `${selectedPatient.weight_kg} kg` : '--'}</span></div>
                          <div className="pp-stat"><span className="pp-stat-label">Chiều cao</span><span className="pp-stat-value">{selectedPatient.height_cm ? `${selectedPatient.height_cm} cm` : '--'}</span></div>
                        </div>
                      </div>

                      {/* Tabs */}
                      <div className="pp-tabs">
                        {PATIENT_PROFILE_TABS.map(tab => (
                          <button
                            key={tab.id}
                            className={`pp-tab ${patientProfileTab === tab.id ? 'active' : ''}`}
                            onClick={() => setPatientProfileTab(tab.id)}
                          >
                            {tab.label}
                          </button>
                        ))}
                      </div>

                      {/* Tổng quan tab content */}
                      {patientProfileTab === 'overview' && (
                        <>
                          <div className="pp-overview-grid">
                            {/* Timeline */}
                            <div className="pp-card pp-timeline-card">
                              <h3>Tóm tắt bệnh án</h3>
                              {selectedPatient.visits.length === 0 ? (
                                <div className="pp-inline-empty">Chưa có lịch sử khám bệnh nào được ghi nhận.</div>
                              ) : (
                                <div className="pp-timeline">
                                  {selectedPatient.visits.map((visit, idx) => (
                                    <div key={visit.id} className="pp-timeline-item">
                                      <div className={`pp-timeline-dot ${idx === 0 ? 'latest' : ''}`} />
                                      <div className="pp-timeline-content">
                                        <div className="pp-timeline-date">{formatDateVN(visit.visit_date)}</div>
                                        <div className="pp-timeline-title-row">
                                          <span className="pp-timeline-title">{visit.title || 'Khám bệnh'}</span>
                                          {idx === 0 && <span className="pp-badge-latest">Mới nhất</span>}
                                        </div>
                                        {visit.symptoms && <div className="pp-timeline-symptoms">{visit.symptoms}</div>}
                                        {visit.doctor_name && <div className="pp-timeline-doctor">BS. {visit.doctor_name}</div>}
                                      </div>
                                      <ChevronRight size={16} className="pp-timeline-chevron" />
                                    </div>
                                  ))}
                                </div>
                              )}
                              {selectedPatient.visits.length > 0 && (
                                <button className="pp-link-btn" onClick={() => setPatientProfileTab('history')}>Xem tất cả lịch sử khám</button>
                              )}
                            </div>

                            {/* Latest visit detail */}
                            <div className="pp-card pp-visit-detail-card">
                              {selectedPatient.visits.length === 0 ? (
                                <>
                                  <h3>Lần khám gần nhất</h3>
                                  <div className="pp-inline-empty">Bệnh nhân chưa có lần khám nào được ghi nhận.</div>
                                </>
                              ) : (() => {
                                const latest = selectedPatient.visits[0];
                                const symptomList = (latest.symptoms || '').split('\n').map(s => s.trim()).filter(Boolean);
                                const treatmentList = (latest.treatment || '').split('\n').map(s => s.trim()).filter(Boolean);
                                return (
                                  <>
                                    <div className="pp-visit-detail-header">
                                      <h3>Lần khám gần nhất - {formatDateVN(latest.visit_date)}</h3>
                                      <button className="pp-link-btn" onClick={() => setPatientProfileTab('history')}>Xem chi tiết</button>
                                    </div>
                                    <div className="pp-visit-detail-grid">
                                      <div>
                                        <h4>Triệu chứng chính</h4>
                                        {symptomList.length === 0 ? <p className="pp-muted">Không có ghi nhận.</p> : (
                                          <ul>{symptomList.map((s, i) => <li key={i}>{s}</li>)}</ul>
                                        )}
                                      </div>
                                      <div>
                                        <h4>Chẩn đoán</h4>
                                        {latest.diagnosis_primary && (
                                          <div className="pp-diagnosis-row">
                                            <span>{latest.diagnosis_primary}</span>
                                            <span className="pp-pill pp-pill-primary">Chẩn đoán chính</span>
                                          </div>
                                        )}
                                        {latest.diagnosis_secondary && (
                                          <div className="pp-diagnosis-row">
                                            <span>{latest.diagnosis_secondary}</span>
                                            <span className="pp-pill pp-pill-secondary">Chẩn đoán phụ</span>
                                          </div>
                                        )}
                                        {!latest.diagnosis_primary && !latest.diagnosis_secondary && <p className="pp-muted">Chưa có chẩn đoán.</p>}
                                      </div>
                                      <div>
                                        <h4>Điều trị</h4>
                                        {treatmentList.length === 0 ? <p className="pp-muted">Không có ghi nhận.</p> : (
                                          <ul>{treatmentList.map((s, i) => <li key={i}>{s}</li>)}</ul>
                                        )}
                                        {treatmentList.length > 0 && (
                                          <button className="pp-btn-outline" onClick={() => setPatientProfileTab('treatment')}>
                                            <FileText size={13} /> Xem đơn thuốc
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                    {latest.doctor_notes && (
                                      <div className="pp-doctor-notes">
                                        <h4>Ghi chú của bác sĩ</h4>
                                        <p>{latest.doctor_notes}</p>
                                      </div>
                                    )}
                                  </>
                                );
                              })()}
                            </div>
                          </div>

                          {/* Important medical info cards */}
                          <div className="pp-info-section">
                            <h3>Thông tin y tế quan trọng</h3>
                            <div className="pp-info-cards">
                              {/* Màu ở bốn ô này phải MANG NGHĨA. Trước đây ô Dị ứng luôn
                                  đỏ kể cả khi trống, nên đỏ mất hết sức cảnh báo: liếc vào
                                  không phân biệt được "có dị ứng" với "chưa ghi gì". Nay ô
                                  trống về trung tính, chỉ ô có dữ liệu thật mới mang màu. */}
                              <div className={`pp-info-card ${hasClinicalValue(selectedPatient.allergies) ? 'danger' : 'empty'}`}>
                                <div className="pp-info-icon"><Ban size={16} /></div>
                                <div>
                                  <div className="pp-info-title">Dị ứng</div>
                                  <div className="pp-info-value">{selectedPatient.allergies || 'Không có'}</div>
                                </div>
                              </div>
                              <div className={`pp-info-card ${hasClinicalValue(selectedPatient.chronic_conditions) ? 'warning' : 'empty'}`}>
                                <div className="pp-info-icon"><Stethoscope size={16} /></div>
                                <div>
                                  <div className="pp-info-title">Chẩn đoán</div>
                                  <div className="pp-info-value">{selectedPatient.chronic_conditions || 'Không có'}</div>
                                </div>
                              </div>
                              <div className={`pp-info-card ${hasClinicalValue(selectedPatient.surgical_history) ? 'info' : 'empty'}`}>
                                <div className="pp-info-icon"><FileText size={16} /></div>
                                <div>
                                  <div className="pp-info-title">Tiền sử bệnh</div>
                                  <div className="pp-info-value">{selectedPatient.surgical_history || 'Chưa có tiền sử bệnh'}</div>
                                </div>
                              </div>
                              <div className={`pp-info-card ${hasClinicalValue(selectedPatient.family_history) ? 'purple' : 'empty'}`}>
                                <div className="pp-info-icon"><UsersRound size={16} /></div>
                                <div>
                                  <div className="pp-info-title">Tiền sử gia đình</div>
                                  <div className="pp-info-value">
                                    {selectedPatient.family_history
                                      ? selectedPatient.family_history.split('\n').filter(Boolean).map((l, i) => <div key={i}>{l}</div>)
                                      : 'Không có'}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </>
                      )}

                      {patientProfileTab === 'history' && (() => {
                        const allVisits = selectedPatient.visits || [];
                        const now = Date.now();
                        const rangeMs = { '7d': 7 * 86400000, '30d': 30 * 86400000, '90d': 90 * 86400000, '1y': 365 * 86400000 };
                        const doctorOptions = [...new Set(allVisits.map(v => v.doctor_name).filter(Boolean))];

                        const filteredVisits = allVisits.filter(visit => {
                          if (historyStatus !== 'all' && (visit.status || 'in_progress') !== historyStatus) return false;
                          if (historyDoctor !== 'all' && visit.doctor_name !== historyDoctor) return false;
                          if (historyDiagnosisSearch.trim()) {
                            const q = stripDiacriticsVN(historyDiagnosisSearch.trim());
                            const hay = stripDiacriticsVN(`${visit.diagnosis_primary || ''} ${visit.title || ''}`);
                            if (!hay.includes(q)) return false;
                          }
                          if (historyDateRange !== 'all') {
                            const t = new Date(`${visit.visit_date}T00:00:00`).getTime();
                            if (Number.isNaN(t) || now - t > rangeMs[historyDateRange]) return false;
                          }
                          return true;
                        });

                        const hasHistoryFilters = historyDateRange !== 'all' || historyStatus !== 'all' || historyDiagnosisSearch.trim() !== '' || historyDoctor !== 'all';
                        const resetHistoryFilters = () => {
                          setHistoryDateRange('all'); setHistoryStatus('all'); setHistoryDiagnosisSearch(''); setHistoryDoctor('all');
                        };

                        const totalMeds = allVisits.reduce((sum, v) => sum + (v.medications || []).length, 0);
                        const totalLabTests = (selectedPatient.attachments || []).filter(a => classifyAttachmentCategory(a) === 'lab').length;
                        const latestVisit = allVisits[0] || null;
                        const openVisitId = expandedHistoryVisitId || (filteredVisits[0] && filteredVisits[0].id) || null;
                        const goToTreatment = (visitId) => { setActiveTreatmentVisitId(visitId); setPatientProfileTab('treatment'); };

                        return (
                          <div className="pp-histtab">
                            {/* Left: filters + quick stats */}
                            <div className="pp-hist-sidebar">
                              <div className="pp-card pp-doc-side-card">
                                <h4>Bộ lọc</h4>
                                <div className="pp-doc-filter-group">
                                  <label>Khoảng thời gian</label>
                                  <div className="pp-doc-select-wrap pp-doc-select-has-icon">
                                    <Calendar size={14} className="pp-doc-select-icon" />
                                    <select value={historyDateRange} onChange={e => setHistoryDateRange(e.target.value)}>
                                      <option value="all">Tất cả thời gian</option>
                                      <option value="7d">7 ngày qua</option>
                                      <option value="30d">30 ngày qua</option>
                                      <option value="90d">3 tháng qua</option>
                                      <option value="1y">1 năm qua</option>
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <div className="pp-doc-filter-group">
                                  <label>Loại khám</label>
                                  <div className="pp-doc-select-wrap">
                                    <select value={historyStatus} onChange={e => setHistoryStatus(e.target.value)}>
                                      <option value="all">Tất cả</option>
                                      <option value="in_progress">Đang điều trị</option>
                                      <option value="completed">Hoàn thành</option>
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <div className="pp-doc-filter-group">
                                  <label>Chẩn đoán chính</label>
                                  <input
                                    type="text"
                                    className="pp-hist-search-input"
                                    value={historyDiagnosisSearch}
                                    onChange={e => setHistoryDiagnosisSearch(e.target.value)}
                                    placeholder="Tìm kiếm chẩn đoán..."
                                  />
                                </div>
                                <div className="pp-doc-filter-group">
                                  <label>Bác sĩ khám</label>
                                  <div className="pp-doc-select-wrap">
                                    <select value={historyDoctor} onChange={e => setHistoryDoctor(e.target.value)}>
                                      <option value="all">Tất cả bác sĩ</option>
                                      {doctorOptions.map(d => <option key={d} value={d}>BS. {d}</option>)}
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <button className="pp-doc-reset-btn" onClick={resetHistoryFilters} disabled={!hasHistoryFilters}>
                                  <RotateCcw size={13} /> Đặt lại bộ lọc
                                </button>
                              </div>

                              <div className="pp-card pp-doc-side-card">
                                <h4>Thống kê nhanh</h4>
                                <div className="pp-hist-stats-list">
                                  <div className="pp-hist-stat-row">
                                    <div className="pp-hist-stat-icon pp-hist-stat-blue"><Users size={15} /></div>
                                    <div className="pp-hist-stat-info">
                                      <span className="pp-hist-stat-label">Tổng số lần khám</span>
                                      <span className="pp-hist-stat-value">{allVisits.length}</span>
                                    </div>
                                  </div>
                                  <div className="pp-hist-stat-row">
                                    <div className="pp-hist-stat-icon pp-hist-stat-green"><Calendar size={15} /></div>
                                    <div className="pp-hist-stat-info">
                                      <span className="pp-hist-stat-label">Lần khám gần nhất</span>
                                      <span className="pp-hist-stat-value">{latestVisit ? formatDateVN(latestVisit.visit_date) : '--'}</span>
                                    </div>
                                  </div>
                                  <div className="pp-hist-stat-row">
                                    <div className="pp-hist-stat-icon pp-hist-stat-orange"><Pill size={15} /></div>
                                    <div className="pp-hist-stat-info">
                                      <span className="pp-hist-stat-label">Tổng thuốc đã kê</span>
                                      <span className="pp-hist-stat-value">{totalMeds} đơn</span>
                                    </div>
                                  </div>
                                  <div className="pp-hist-stat-row">
                                    <div className="pp-hist-stat-icon pp-hist-stat-purple"><FlaskConical size={15} /></div>
                                    <div className="pp-hist-stat-info">
                                      <span className="pp-hist-stat-label">Tổng xét nghiệm</span>
                                      <span className="pp-hist-stat-value">{totalLabTests} lần</span>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Middle: visit timeline */}
                            <div className="pp-hist-main">
                              <div className="pp-hist-main-header">
                                <h3 className="pp-hist-main-title">Lịch sử khám bệnh</h3>
                              </div>
                              {filteredVisits.length === 0 ? (
                                <div className="pp-card"><div className="pp-inline-empty">Không tìm thấy lần khám nào phù hợp với bộ lọc.</div></div>
                              ) : (
                                <div className="pp-hist-timeline">
                                  {filteredVisits.map(visit => {
                                    const isOpen = visit.id === openVisitId;
                                    const statusMeta = TREATMENT_STATUS_META[visit.status] || TREATMENT_STATUS_META.completed;
                                    const symptomList = (visit.symptoms || '').split('\n').map(s => s.trim()).filter(Boolean);
                                    const treatmentList = (visit.treatment || '').split('\n').map(s => s.trim()).filter(Boolean);
                                    const subclinicalList = (visit.subclinical_orders || '').split('\n').map(s => s.trim()).filter(Boolean);
                                    const medCount = (visit.medications || []).length;
                                    const sameDayAttachments = (selectedPatient.attachments || []).filter(a => (a.uploaded_at || '').slice(0, 10) === visit.visit_date);
                                    const labCount = sameDayAttachments.filter(a => classifyAttachmentCategory(a) === 'lab').length;
                                    const imgCount = sameDayAttachments.filter(a => ['imaging', 'xray', 'ultrasound', 'endoscopy'].includes(classifyAttachmentCategory(a))).length;
                                    const docCount = sameDayAttachments.filter(a => classifyAttachmentCategory(a) === 'other').length;

                                    return (
                                      <div key={visit.id} className="pp-hist-item">
                                        <div className="pp-hist-dot-col">
                                          <span className={`pp-hist-dot ${isOpen ? 'open' : ''}`} />
                                        </div>
                                        <div className="pp-hist-date-col">
                                          <span className="pp-hist-date">{formatDateVN(visit.visit_date)}</span>
                                          {formatTimeVN(visit.visit_date) && <span className="pp-hist-time">{formatTimeVN(visit.visit_date)}</span>}
                                        </div>

                                        {isOpen ? (
                                          <div className="pp-hist-card-open">
                                            <div className="pp-hist-card-header">
                                              <div className="pp-hist-card-header-left">
                                                <span className="pp-hist-card-title">{visit.title || 'Khám bệnh'}</span>
                                                <span className={`pp-status-badge ${statusMeta.className}`}>{statusMeta.label}</span>
                                              </div>
                                              <button
                                                type="button"
                                                className="pp-hist-collapse-btn"
                                                title="Thu nhỏ"
                                                onClick={(e) => { e.stopPropagation(); setExpandedHistoryVisitId(null); }}
                                              >
                                                <ChevronUp size={16} />
                                              </button>
                                            </div>

                                            <div className="pp-hist-card-grid">
                                              <div>
                                                <div className="pp-hist-col-label">Triệu chứng</div>
                                                {symptomList.length ? (
                                                  <ul className="pp-hist-bullets">{symptomList.map((s, i) => <li key={i}>{s}</li>)}</ul>
                                                ) : <p className="pp-muted">Chưa ghi nhận.</p>}
                                              </div>
                                              <div>
                                                <div className="pp-hist-col-label">Chẩn đoán</div>
                                                <p className="pp-hist-col-text">{visit.diagnosis_primary || 'Chưa có chẩn đoán.'}</p>
                                              </div>
                                              <div>
                                                <div className="pp-hist-col-label">Điều trị</div>
                                                {treatmentList.length ? (
                                                  <ul className="pp-hist-bullets">{treatmentList.map((s, i) => <li key={i}>{s}</li>)}</ul>
                                                ) : <p className="pp-muted">Chưa có.</p>}
                                              </div>
                                              <div>
                                                <div className="pp-hist-col-label">Chỉ định CLS</div>
                                                {subclinicalList.length ? (
                                                  <ul className="pp-hist-bullets">{subclinicalList.map((s, i) => <li key={i}>{s}</li>)}</ul>
                                                ) : <p className="pp-muted">Chưa có chỉ định.</p>}
                                              </div>
                                              <div>
                                                <div className="pp-hist-col-label">Ghi chú</div>
                                                <p className="pp-hist-col-text">{visit.doctor_notes || 'Không có ghi chú.'}</p>
                                              </div>
                                            </div>

                                            <div className="pp-hist-card-footer">
                                              <div className="pp-hist-chips">
                                                {medCount > 0 && <span className="pp-hist-chip"><Pill size={12} /> {medCount} đơn thuốc</span>}
                                                {labCount > 0 && <span className="pp-hist-chip"><FlaskConical size={12} /> {labCount} xét nghiệm</span>}
                                                {imgCount > 0 && <span className="pp-hist-chip"><ImageIcon size={12} /> {imgCount} hình ảnh</span>}
                                                {docCount > 0 && <span className="pp-hist-chip"><FileText size={12} /> {docCount} tài liệu</span>}
                                              </div>
                                              <div className="pp-hist-footer-actions">
                                                <button className="pp-icon-btn" title="Xóa lần khám" onClick={() => handleDeleteVisit(visit.id)}><Trash2 size={14} /></button>
                                                <button className="pp-link-btn pp-hist-detail-link" onClick={() => goToTreatment(visit.id)}>Xem chi tiết</button>
                                              </div>
                                            </div>
                                          </div>
                                        ) : (
                                          <div className="pp-hist-card-closed" role="button" tabIndex={0} onClick={() => setExpandedHistoryVisitId(visit.id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpandedHistoryVisitId(visit.id); }}>
                                            <div className="pp-hist-closed-main">
                                              <span className="pp-hist-card-title">{visit.title || 'Khám bệnh'}</span>
                                              {(visit.symptoms || '').trim() && <span className="pp-hist-closed-sub">{(visit.symptoms || '').split('\n')[0]}</span>}
                                            </div>
                                            <div className="pp-hist-closed-right">
                                              <span className={`pp-status-badge pp-status-sm ${statusMeta.className}`}>{statusMeta.label}</span>
                                              <span className="pp-hist-closed-doctor">{visit.doctor_name ? `BS. ${visit.doctor_name}` : ''}</span>
                                              <button className="pp-icon-btn" title="Xóa lần khám" onClick={(e) => { e.stopPropagation(); handleDeleteVisit(visit.id); }}><Trash2 size={14} /></button>
                                              <ChevronDown size={15} className="pp-hist-closed-chevron" />
                                            </div>
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                              {filteredVisits.length > 0 && <div className="pp-hist-footer-note">Đã hiển thị tất cả</div>}
                            </div>
                          </div>
                        );
                      })()}

                      {patientProfileTab === 'treatment' && (
                        <div className="pp-tp-wrap">
                          <div className="pp-tp-topbar">
                            <div className="pp-tp-visit-select">
                              <label>Chọn lần khám</label>
                              <div className="pp-doc-select-wrap">
                                <select
                                  value={currentTreatmentVisit ? currentTreatmentVisit.id : ''}
                                  onChange={e => setActiveTreatmentVisitId(e.target.value)}
                                  disabled={!selectedPatient.visits.length}
                                >
                                  {!selectedPatient.visits.length && <option value="">Chưa có lần khám nào</option>}
                                  {selectedPatient.visits.map(v => (
                                    <option key={v.id} value={v.id}>
                                      {formatDateVN(v.visit_date)} - {v.diagnosis_primary || v.title || 'Khám bệnh'}
                                    </option>
                                  ))}
                                </select>
                                <ChevronDown size={14} className="pp-doc-select-chevron" />
                              </div>
                            </div>
                            <div className="pp-tp-topbar-actions">
                              <button className="pp-btn-outline" onClick={handlePrintTreatmentPlan} disabled={!currentTreatmentVisit}>
                                <Printer size={14} /> In kế hoạch
                              </button>
                              <button className="pp-btn-add" onClick={openAddVisitPanel}>
                                <Plus size={14} /> Tạo kế hoạch mới
                              </button>
                            </div>
                          </div>

                          {!currentTreatmentVisit ? (
                            <div className="pp-card">
                              <div className="pp-empty-state">
                                <div className="pp-empty-icon"><ClipboardList size={26} /></div>
                                <h3>Chưa có kế hoạch điều trị nào</h3>
                                <p>Tạo kế hoạch điều trị đầu tiên cho bệnh nhân để bắt đầu theo dõi chẩn đoán, thuốc và lịch tái khám.</p>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="pp-tp-grid">
                                {/* 1. Chẩn đoán */}
                                <div className="pp-card pp-tp-card">
                                  <div className="pp-tp-card-header">
                                    <h4><span className="pp-section-badge">1</span> Chẩn đoán</h4>
                                    <div className="pp-tp-header-actions">
                                      {currentTreatmentVisit.diagnosis_primary && <span className="pp-tp-confirmed-tag">Chẩn đoán chính</span>}
                                      <button className="pp-link-btn" onClick={() => handleAiSuggestDiagnosis(currentTreatmentVisit)} disabled={aiSuggestLoading}>
                                        {aiSuggestLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Gợi ý từ AI
                                      </button>
                                      {!isEditingDiagnosis && (
                                        <button className="pp-link-btn" onClick={() => openDiagnosisEdit(currentTreatmentVisit)}><PencilLine size={12} /> Sửa</button>
                                      )}
                                    </div>
                                  </div>

                                  {aiReasoningNote && (
                                    <div className="pp-tp-ai-note">
                                      <Sparkles size={13} />
                                      <span>{aiReasoningNote}</span>
                                      <button className="pp-icon-btn" onClick={() => { setAiReasoningNote(''); setAiAgentTrace([]); setAiAgentSources([]); }}><X size={13} /></button>
                                    </div>
                                  )}

                                  {aiAgentTrace.length > 0 && (
                                    <div className="pp-agent-trace">
                                      <button className="pp-agent-trace-toggle" onClick={() => setAiAgentTraceExpanded(v => !v)}>
                                        {aiAgentTraceExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                        Agent đã tra cứu {aiAgentTrace.length} bước trước khi kết luận
                                      </button>
                                      {aiAgentTraceExpanded && (
                                        <div className="pp-agent-trace-list">
                                          {aiAgentTrace.map((step, idx) => (
                                            <div className="pp-agent-trace-step" key={idx}>
                                              {step.tool === 'tra_cuu_duoc_thu' ? <Search size={12} /> : <FileText size={12} />}
                                              <div>
                                                <div className="pp-agent-trace-step-label">{step.label}</div>
                                                {step.output_summary && (
                                                  <div className="pp-agent-trace-step-output">{step.output_summary}</div>
                                                )}
                                              </div>
                                            </div>
                                          ))}
                                          {aiAgentSources.length > 0 && (
                                            <div className="pp-agent-source-chips">
                                              {aiAgentSources.map((src, idx) => (
                                                <button
                                                  key={idx}
                                                  className="pp-agent-source-chip"
                                                  onClick={() => handleOpenLibraryPreview(src.doc_name, parseInt(String(src.page_num).replace(/[^\d]/g, ''), 10) || 1)}
                                                  title={src.snippet}
                                                >
                                                  <BookOpen size={11} /> {sourceTitle(src)} · {src.page_num}
                                                </button>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  {isEditingDiagnosis ? (
                                    <div className="pp-tp-edit-form">
                                      <label>Chẩn đoán chính</label>
                                      <input type="text" value={diagnosisDraft.primary} onChange={e => setDiagnosisDraft(d => ({ ...d, primary: e.target.value }))} placeholder="Ví dụ: Viêm họng cấp do virus (J02.9)" />
                                      <label>Chẩn đoán phân biệt (mỗi dòng một chẩn đoán)</label>
                                      <textarea rows={4} value={diagnosisDraft.differentials} onChange={e => setDiagnosisDraft(d => ({ ...d, differentials: e.target.value }))} placeholder={'Viêm họng do liên cầu khuẩn (J02.0)\nViêm amidan cấp (J03.9)'} />
                                      <label>Khám lâm sàng</label>
                                      <textarea rows={4} value={diagnosisDraft.exam} onChange={e => setDiagnosisDraft(d => ({ ...d, exam: e.target.value }))} placeholder="Niêm mạc họng viêm, không có mủ, không hạch cổ to." />
                                      <div className="pp-tp-edit-actions">
                                        <button className="pp-btn-ghost" onClick={() => setIsEditingDiagnosis(false)}>Hủy</button>
                                        <button className="pp-btn-add pp-btn-sm" onClick={() => handleSaveDiagnosis(currentTreatmentVisit.id)}>Lưu</button>
                                      </div>
                                    </div>
                                  ) : (
                                    <>
                                      {currentTreatmentVisit.diagnosis_primary ? (() => {
                                        const { name, code } = parseDiagnosisPrimary(currentTreatmentVisit.diagnosis_primary);
                                        const basis = [currentTreatmentVisit.symptoms, currentTreatmentVisit.exam_findings].filter(Boolean).join('. ');
                                        return (
                                          <div className="pp-tp-diag-box">
                                            <div className="pp-tp-diag-box-top">
                                              {code && <span className="pp-tp-diag-code">{code}</span>}
                                              <span className="pp-tp-diag-name">{name}</span>
                                              {!!currentTreatmentVisit.diagnosis_confidence && (
                                                <span className={`pp-confidence-badge ${confidenceMeta(currentTreatmentVisit.diagnosis_confidence).className}`}>
                                                  Độ tin cậy: {confidenceMeta(currentTreatmentVisit.diagnosis_confidence).label} ({currentTreatmentVisit.diagnosis_confidence}%)
                                                </span>
                                              )}
                                            </div>
                                            <p className="pp-tp-diag-basis"><strong>Dựa trên:</strong> {basis || 'Chưa ghi nhận.'}</p>
                                          </div>
                                        );
                                      })() : <p className="pp-muted">Chưa có chẩn đoán chính.</p>}

                                      {(currentTreatmentVisit.differential_diagnoses || []).length > 0 ? (
                                        <>
                                          <div className="pp-tp-subhead">Chẩn đoán phân biệt</div>
                                          <div className="pp-diag-top5-table">
                                            <div className="pp-diag-top5-row pp-diag-top5-head">
                                              <span>STT</span><span>Chẩn đoán</span><span>ICD-10</span><span>Độ tin cậy</span><span>Ghi chú</span>
                                            </div>
                                            {currentTreatmentVisit.differential_diagnoses.map((d, i) => {
                                              const meta = confidenceMeta(d.confidence);
                                              return (
                                                <div key={i} className="pp-diag-top5-row">
                                                  <span>{i + 1}</span>
                                                  <span>{d.name}</span>
                                                  <span>{d.icd10 || '—'}</span>
                                                  <span className={`pp-confidence-dot ${meta.className}`}>{meta.label} ({d.confidence}%)</span>
                                                  <span>{d.note || '—'}</span>
                                                </div>
                                              );
                                            })}
                                          </div>
                                          <button type="button" className="pp-link-btn pp-diag-reasoning-toggle" onClick={() => setShowDiagnosisReasoning(v => !v)}>
                                            {showDiagnosisReasoning ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Xem chi tiết lý do gợi ý
                                          </button>
                                          {showDiagnosisReasoning && (
                                            <ul className="pp-tp-bullets pp-diag-reasoning-list">
                                              {currentTreatmentVisit.differential_diagnoses.filter(d => d.reasoning).map((d, i) => (
                                                <li key={i}><strong>{d.name}:</strong> {d.reasoning}</li>
                                              ))}
                                            </ul>
                                          )}
                                        </>
                                      ) : currentTreatmentVisit.diagnosis_secondary && (
                                        <>
                                          <div className="pp-tp-subhead">Chẩn đoán phân biệt</div>
                                          <ul className="pp-tp-bullets">
                                            {currentTreatmentVisit.diagnosis_secondary.split('\n').map(s => s.trim()).filter(Boolean).map((s, i) => <li key={i}>{s}</li>)}
                                          </ul>
                                        </>
                                      )}

                                      <div className="pp-tp-diag-note-head">
                                        <div className="pp-tp-subhead">Ghi chú chẩn đoán</div>
                                        {!isEditingDiagnosisNote && <button className="pp-link-btn" onClick={() => openDiagnosisNoteEdit(currentTreatmentVisit)}><PencilLine size={12} /> Sửa</button>}
                                      </div>
                                      {isEditingDiagnosisNote ? (
                                        <div className="pp-tp-edit-form">
                                          <textarea rows={3} maxLength={1000} value={diagnosisNoteDraft} onChange={e => setDiagnosisNoteDraft(e.target.value)} placeholder="Nhập ghi chú thêm về chẩn đoán (nếu có)..." />
                                          <div className="pp-diag-note-counter">{diagnosisNoteDraft.length}/1000</div>
                                          <div className="pp-tp-edit-actions">
                                            <button className="pp-btn-ghost" onClick={() => setIsEditingDiagnosisNote(false)}>Hủy</button>
                                            <button className="pp-btn-add pp-btn-sm" onClick={() => handleSaveDiagnosisNote(currentTreatmentVisit.id)}>Lưu</button>
                                          </div>
                                        </div>
                                      ) : currentTreatmentVisit.diagnosis_note && (
                                        <p className="pp-tp-basis">{currentTreatmentVisit.diagnosis_note}</p>
                                      )}
                                    </>
                                  )}
                                </div>

                                {/* 3. Đơn thuốc */}
                                <div className="pp-card pp-tp-card">
                                  <div className="pp-tp-card-header">
                                    <h4><span className="pp-section-badge">3</span> Đơn thuốc</h4>
                                    <button className="pp-btn-outline" onClick={openAddMedication}><Plus size={13} /> Thêm thuốc</button>
                                  </div>

                                  {(currentTreatmentVisit.medications || []).length === 0 && !isAddingMedication ? (
                                    <div className="pp-inline-empty">Chưa có thuốc điều trị nào được kê.</div>
                                  ) : (currentTreatmentVisit.medications || []).length > 0 && (
                                    <div className="pp-tp-rx-table">
                                      <div className="pp-tp-rx-row pp-tp-rx-head">
                                        <span>#</span><span>Thuốc</span><span>Cách dùng – Liều dùng</span><span>Số lượng</span><span></span>
                                      </div>
                                      {currentTreatmentVisit.medications.map((m, i) => (
                                        <div key={i} className="pp-tp-rx-row">
                                          <span className="pp-tp-rx-idx">{i + 1}</span>
                                          <span className="pp-tp-rx-name">
                                            <strong>{m.name}</strong>
                                            {m.form && <small>{m.form}</small>}
                                          </span>
                                          <span className="pp-tp-rx-usage">
                                            {!!(m.dosage || m.frequency) && <div>{[m.dosage, m.frequency].filter(Boolean).join(', ')}</div>}
                                            {(m.instructions || '').split('\n').map(s => s.trim()).filter(Boolean).map((line, li) => <small key={li}>{line}</small>)}
                                          </span>
                                          <span className="pp-tp-rx-qty">{m.quantity || '—'}</span>
                                          <button className="pp-icon-btn" onClick={() => handleDeleteMedication(currentTreatmentVisit, i)}><Trash2 size={14} /></button>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  {isAddingMedication && (
                                    <div className="pp-tp-med-add-form">
                                      <div className="pp-form-row">
                                        <div className="pp-form-group"><label>Tên thuốc</label><input type="text" value={medDraft.name} onChange={e => setMedDraft(d => ({ ...d, name: e.target.value }))} placeholder="Ví dụ: Paracetamol 500mg" autoFocus /></div>
                                        <div className="pp-form-group"><label>Dạng bào chế</label><input type="text" value={medDraft.form} onChange={e => setMedDraft(d => ({ ...d, form: e.target.value }))} placeholder="Viên nén" /></div>
                                      </div>
                                      <div className="pp-form-row">
                                        <div className="pp-form-group"><label>Liều dùng</label><input type="text" value={medDraft.dosage} onChange={e => setMedDraft(d => ({ ...d, dosage: e.target.value }))} placeholder="Uống 1 viên/lần" /></div>
                                        <div className="pp-form-group"><label>Thời gian</label><input type="text" value={medDraft.frequency} onChange={e => setMedDraft(d => ({ ...d, frequency: e.target.value }))} placeholder="Ngày 3 lần" /></div>
                                      </div>
                                      <div className="pp-form-row">
                                        <div className="pp-form-group"><label>Số lượng</label><input type="text" value={medDraft.quantity} onChange={e => setMedDraft(d => ({ ...d, quantity: e.target.value }))} placeholder="10 viên" /></div>
                                        <div className="pp-form-group"><label>Hướng dẫn</label><input type="text" value={medDraft.instructions} onChange={e => setMedDraft(d => ({ ...d, instructions: e.target.value }))} placeholder="Sau ăn" /></div>
                                      </div>
                                      <div className="pp-tp-edit-actions">
                                        <button className="pp-btn-ghost" onClick={() => setIsAddingMedication(false)}>Hủy</button>
                                        <button className="pp-btn-add pp-btn-sm" onClick={() => handleSaveMedication(currentTreatmentVisit)}>Thêm thuốc</button>
                                      </div>
                                    </div>
                                  )}

                                  <div className="pp-tp-note-box">
                                    <div className="pp-tp-note-box-head">
                                      <span className="pp-tp-note-label">Lưu ý:</span>
                                      {!isEditingNoDrug && <button className="pp-link-btn" onClick={() => openNoDrugEdit(currentTreatmentVisit)}><PencilLine size={12} /> Sửa</button>}
                                    </div>
                                    {isEditingNoDrug ? (
                                      <div className="pp-tp-edit-form">
                                        <textarea rows={3} value={noDrugDraft} onChange={e => setNoDrugDraft(e.target.value)} placeholder={'Uống thuốc đúng liều, đủ thời gian.\nKhông tự ý ngưng thuốc khi chưa hết triệu chứng.'} />
                                        <div className="pp-tp-edit-actions">
                                          <button className="pp-btn-ghost" onClick={() => setIsEditingNoDrug(false)}>Hủy</button>
                                          <button className="pp-btn-add pp-btn-sm" onClick={() => handleSaveNoDrug(currentTreatmentVisit.id)}>Lưu</button>
                                        </div>
                                      </div>
                                    ) : (
                                      <p className="pp-tp-note-text">
                                        {(currentTreatmentVisit.no_drug_recommendations || '').trim() === ''
                                          ? 'Chưa có lưu ý nào.'
                                          : currentTreatmentVisit.no_drug_recommendations.split('\n').map(s => s.trim()).filter(Boolean).join(' ')}
                                      </p>
                                    )}
                                  </div>
                                </div>

                                {/* 2. Kế hoạch điều trị */}
                                <div className="pp-card pp-tp-card">
                                  <div className="pp-tp-card-header">
                                    <h4><span className="pp-section-badge">2</span> Kế hoạch điều trị</h4>
                                    {!isEditingPlan && !isEditingFollowup && (
                                      <button className="pp-link-btn" onClick={() => { openPlanEdit(currentTreatmentVisit); openFollowupEdit(currentTreatmentVisit); }}><PencilLine size={12} /> Sửa kế hoạch</button>
                                    )}
                                  </div>
                                  {(isEditingPlan || isEditingFollowup) ? (
                                    <div className="pp-tp-edit-form">
                                      <label>Mục tiêu điều trị (mỗi dòng một mục tiêu)</label>
                                      <textarea rows={3} value={planDraft.goals} onChange={e => setPlanDraft(d => ({ ...d, goals: e.target.value }))} placeholder={'Giảm nhanh triệu chứng\nNgăn ngừa biến chứng'} />
                                      <div className="pp-form-row">
                                        <div className="pp-form-group"><label>Phương pháp điều trị</label><input type="text" value={planDraft.treatment_method} onChange={e => setPlanDraft(d => ({ ...d, treatment_method: e.target.value }))} placeholder="Nội khoa" /></div>
                                        <div className="pp-form-group"><label>Thời gian dự kiến</label><input type="text" value={planDraft.protocol_duration} onChange={e => setPlanDraft(d => ({ ...d, protocol_duration: e.target.value }))} placeholder="5 - 7 ngày" /></div>
                                      </div>
                                      <label>Chế độ</label>
                                      <textarea rows={2} value={planDraft.diet_regimen} onChange={e => setPlanDraft(d => ({ ...d, diet_regimen: e.target.value }))} placeholder="Nghỉ ngơi, uống nhiều nước ấm, ăn thức ăn mềm, dễ nuốt." />
                                      <label>Lưu ý</label>
                                      <textarea rows={2} value={planDraft.precautions} onChange={e => setPlanDraft(d => ({ ...d, precautions: e.target.value }))} placeholder="Tránh khói bụi, không hút thuốc lá, không uống rượu bia." />
                                      <label>Mục đích / tiêu chí tái khám</label>
                                      <textarea rows={2} value={followupDraft.purpose} onChange={e => setFollowupDraft(d => ({ ...d, purpose: e.target.value }))} placeholder="Nếu không cải thiện sau 3 ngày hoặc nặng hơn." />
                                      <label>Ngày hẹn tái khám (nếu có)</label>
                                      <input type="date" value={followupDraft.date} onChange={e => setFollowupDraft(d => ({ ...d, date: e.target.value }))} />
                                      <div className="pp-tp-edit-actions">
                                        <button className="pp-btn-ghost" onClick={() => { setIsEditingPlan(false); setIsEditingFollowup(false); }}>Hủy</button>
                                        <button className="pp-btn-add pp-btn-sm" onClick={async () => { await handleSavePlan(currentTreatmentVisit.id); await handleSaveFollowup(currentTreatmentVisit.id); }}>Lưu</button>
                                      </div>
                                    </div>
                                  ) : (currentTreatmentVisit.goals || []).length === 0
                                    && !currentTreatmentVisit.protocol_duration && !currentTreatmentVisit.followup_purpose
                                    && !currentTreatmentVisit.followup_date && !currentTreatmentVisit.diet_regimen && !currentTreatmentVisit.precautions ? (
                                    <div className="pp-inline-empty">Chưa có kế hoạch điều trị.</div>
                                  ) : (
                                    <div className="pp-tp-plan-icon-rows">
                                      {(currentTreatmentVisit.goals || []).length > 0 && (
                                        <div className="pp-tp-plan-icon-row">
                                          <span className="pp-tp-plan-icon"><Target size={14} /></span>
                                          <span className="pp-tp-plan-label">Mục tiêu điều trị</span>
                                          <span className="pp-tp-plan-value">{currentTreatmentVisit.goals.join(' • ')}</span>
                                        </div>
                                      )}
                                      {currentTreatmentVisit.protocol_duration && (
                                        <div className="pp-tp-plan-icon-row">
                                          <span className="pp-tp-plan-icon"><Clock size={14} /></span>
                                          <span className="pp-tp-plan-label">Thời gian dự kiến</span>
                                          <span className="pp-tp-plan-value">{currentTreatmentVisit.protocol_duration}</span>
                                        </div>
                                      )}
                                      {(currentTreatmentVisit.followup_purpose || currentTreatmentVisit.followup_date) && (
                                        <div className="pp-tp-plan-icon-row">
                                          <span className="pp-tp-plan-icon"><Calendar size={14} /></span>
                                          <span className="pp-tp-plan-label">Tái khám</span>
                                          <span className="pp-tp-plan-value">
                                            {currentTreatmentVisit.followup_date && `${formatDateVN(currentTreatmentVisit.followup_date)}. `}
                                            {currentTreatmentVisit.followup_purpose}
                                          </span>
                                        </div>
                                      )}
                                      {currentTreatmentVisit.diet_regimen && (
                                        <div className="pp-tp-plan-icon-row">
                                          <span className="pp-tp-plan-icon"><Utensils size={14} /></span>
                                          <span className="pp-tp-plan-label">Chế độ</span>
                                          <span className="pp-tp-plan-value">{currentTreatmentVisit.diet_regimen}</span>
                                        </div>
                                      )}
                                      {currentTreatmentVisit.precautions && (
                                        <div className="pp-tp-plan-icon-row">
                                          <span className="pp-tp-plan-icon"><ShieldAlert size={14} /></span>
                                          <span className="pp-tp-plan-label">Lưu ý</span>
                                          <span className="pp-tp-plan-value">{currentTreatmentVisit.precautions}</span>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>

                                {/* 4. Hướng dẫn cho bệnh nhân */}
                                <div className="pp-card pp-tp-card">
                                  <div className="pp-tp-card-header">
                                    <h4><span className="pp-section-badge">4</span> Hướng dẫn cho bệnh nhân</h4>
                                    {!isEditingCare && <button className="pp-link-btn" onClick={() => openCareEdit(currentTreatmentVisit)}><PencilLine size={12} /> Sửa</button>}
                                  </div>
                                  {isEditingCare ? (
                                    <div className="pp-tp-edit-form">
                                      <textarea rows={5} value={careDraft} onChange={e => setCareDraft(e.target.value)} placeholder={'Uống thuốc đúng liều, đúng thời gian theo đơn.\nUống nhiều nước ấm, súc họng nước muối ấm 2-3 lần/ngày.'} />
                                      <div className="pp-tp-edit-actions">
                                        <button className="pp-btn-ghost" onClick={() => setIsEditingCare(false)}>Hủy</button>
                                        <button className="pp-btn-add pp-btn-sm" onClick={() => handleSaveCare(currentTreatmentVisit.id)}>Lưu</button>
                                      </div>
                                    </div>
                                  ) : (
                                    (currentTreatmentVisit.care_instructions || '').trim() === '' ? (
                                      <div className="pp-inline-empty">Chưa có hướng dẫn chăm sóc.</div>
                                    ) : (
                                      <ul className="pp-tp-check-list">
                                        {currentTreatmentVisit.care_instructions.split('\n').map(s => s.trim()).filter(Boolean).map((s, i) => (
                                          <li key={i}><Check size={14} /><span>{s}</span></li>
                                        ))}
                                      </ul>
                                    )
                                  )}
                                </div>
                              </div>

                              <div className="pp-tp-action-bar">
                                <button
                                  type="button"
                                  className="pp-btn-add"
                                  onClick={() => handleToggleTreatmentStatus(currentTreatmentVisit)}
                                  disabled={currentTreatmentVisit.status === 'completed'}
                                >
                                  <Check size={14} /> {currentTreatmentVisit.status === 'completed' ? 'Đã hoàn tất điều trị' : 'Hoàn tất điều trị'}
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      )}

                      {patientProfileTab === 'documents' && (() => {
                        const allAttachments = selectedPatient.attachments || [];
                        const categorized = allAttachments.map(att => ({ ...att, _category: classifyAttachmentCategory(att) }));
                        const categoryCounts = DOC_CATEGORY_ORDER.reduce((acc, id) => {
                          acc[id] = categorized.filter(a => a._category === id).length;
                          return acc;
                        }, {});

                        const now = Date.now();
                        const rangeMs = { '7d': 7 * 86400000, '30d': 30 * 86400000, '90d': 90 * 86400000 };

                        const filtered = categorized.filter(att => {
                          if (docCategory !== 'all' && att._category !== docCategory) return false;
                          if (docSearch.trim() && !stripDiacriticsVN(att.original_name || '').includes(stripDiacriticsVN(docSearch.trim()))) return false;
                          if (docDateRange !== 'all') {
                            const t = new Date(att.uploaded_at).getTime();
                            if (Number.isNaN(t) || now - t > rangeMs[docDateRange]) return false;
                          }
                          if (docStatus !== 'all') {
                            const t = new Date(att.uploaded_at).getTime();
                            const isNew = !Number.isNaN(t) && (now - t) <= 3 * 86400000;
                            if (docStatus === 'new' && !isNew) return false;
                            if (docStatus === 'archived' && isNew) return false;
                          }
                          return true;
                        });

                        const sorted = [...filtered].sort((a, b) => {
                          if (docSort === 'name') return (a.original_name || '').localeCompare(b.original_name || '');
                          if (docSort === 'size') return (b.size_bytes || 0) - (a.size_bytes || 0);
                          if (docSort === 'oldest') return new Date(a.uploaded_at) - new Date(b.uploaded_at);
                          return new Date(b.uploaded_at) - new Date(a.uploaded_at); // newest (default)
                        });

                        const visible = sorted.slice(0, docVisibleCount);
                        const hasFiltersActive = docCategory !== 'all' || docDateRange !== 'all' || docStatus !== 'all';
                        const resetFilters = () => { setDocCategory('all'); setDocDateRange('all'); setDocStatus('all'); setDocVisibleCount(8); };

                        const docCard = (att) => {
                          const meta = DOC_CATEGORY_META[att._category];
                          const CatIcon = meta.icon;
                          const isImage = ['JPG', 'JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF'].includes((att.file_type || '').toUpperCase());
                          const downloadUrl = `/api/patients/${selectedPatient.id}/attachments/${att.id}/download`;

                          const menu = (
                            <DropdownMenu.Root>
                              <DropdownMenu.Trigger asChild>
                                <button className="card-menu-btn" onClick={(e) => e.stopPropagation()} title="Tùy chọn tài liệu">
                                  <MoreHorizontal size={15} />
                                </button>
                              </DropdownMenu.Trigger>
                              <DropdownMenu.Portal>
                                <DropdownMenu.Content className="dropdown-menu-content" align="end" sideOffset={4} onClick={(e) => e.stopPropagation()}>
                                  <DropdownMenu.Item className="dropdown-menu-item" onSelect={() => handleDownloadAttachment(att)}>
                                    <Download size={14} /> Tải xuống
                                  </DropdownMenu.Item>
                                  <DropdownMenu.Separator className="dropdown-menu-separator" />
                                  <DropdownMenu.Item className="dropdown-menu-item danger" onSelect={() => handleDeleteAttachment(att.id)}>
                                    <Trash2 size={14} /> Xóa
                                  </DropdownMenu.Item>
                                </DropdownMenu.Content>
                              </DropdownMenu.Portal>
                            </DropdownMenu.Root>
                          );

                          if (docView === 'list') {
                            return (
                              <div key={att.id} className="pp-doc-row">
                                <div className={`pp-doc-row-icon pp-doc-hue-${getDocFileHue(att.file_type)}`}>
                                  {isImage ? <ImageIcon size={17} /> : <FileText size={17} />}
                                </div>
                                <div className="pp-doc-row-body">
                                  <div className="pp-doc-row-title">{att.original_name}</div>
                                  <div className="pp-doc-row-meta">{formatDateVN(att.uploaded_at)} • {formatTimeVN(att.uploaded_at)} • {formatFileSize(att.size_bytes)}</div>
                                </div>
                                <span className={`pp-doc-tag ${meta.pill}`}><CatIcon size={11} /> {meta.label}</span>
                                {menu}
                              </div>
                            );
                          }

                          return (
                            <div key={att.id} className="pp-doc-card">
                              <div className="pp-doc-card-thumb">
                                {isImage ? (
                                  <AuthedImage url={downloadUrl} alt={att.original_name} />
                                ) : (
                                  <div className={`pp-doc-file-icon pp-doc-hue-${getDocFileHue(att.file_type)}`}>
                                    <FileText size={22} />
                                    <span>{att.file_type || 'FILE'}</span>
                                  </div>
                                )}
                                {menu}
                              </div>
                              <div className="pp-doc-card-body">
                                <div className="pp-doc-card-title">{att.original_name}</div>
                                <div className="pp-doc-card-meta">{formatDateVN(att.uploaded_at)} • {formatTimeVN(att.uploaded_at)} • {formatFileSize(att.size_bytes)}</div>
                                <span className={`pp-doc-tag ${meta.pill}`}><CatIcon size={11} /> {meta.label}</span>
                              </div>
                            </div>
                          );
                        };

                        return (
                          <div className="pp-doctab">
                            {/* Left: categories + filters */}
                            <div className="pp-doc-sidebar">
                              <div className="pp-card pp-doc-side-card">
                                <h4>Danh mục tài liệu</h4>
                                <div className="pp-doc-cat-list">
                                  <button
                                    className={`pp-doc-cat-item ${docCategory === 'all' ? 'active' : ''}`}
                                    onClick={() => { setDocCategory('all'); setDocVisibleCount(8); }}
                                  >
                                    <FileText size={15} />
                                    <span>Tất cả</span>
                                    <span className="pp-doc-cat-count">{allAttachments.length}</span>
                                  </button>
                                  {DOC_CATEGORY_ORDER.map(id => {
                                    const meta = DOC_CATEGORY_META[id];
                                    const Icon = meta.icon;
                                    return (
                                      <button
                                        key={id}
                                        className={`pp-doc-cat-item ${docCategory === id ? 'active' : ''}`}
                                        onClick={() => { setDocCategory(id); setDocVisibleCount(8); }}
                                      >
                                        <Icon size={15} />
                                        <span>{meta.label}</span>
                                        <span className="pp-doc-cat-count">{categoryCounts[id]}</span>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>

                              <div className="pp-card pp-doc-side-card">
                                <h4>Bộ lọc</h4>
                                <div className="pp-doc-filter-group">
                                  <label>Khoảng thời gian</label>
                                  <div className="pp-doc-select-wrap pp-doc-select-has-icon">
                                    <Calendar size={14} className="pp-doc-select-icon" />
                                    <select value={docDateRange} onChange={e => { setDocDateRange(e.target.value); setDocVisibleCount(8); }}>
                                      <option value="all">Tất cả thời gian</option>
                                      <option value="7d">7 ngày qua</option>
                                      <option value="30d">30 ngày qua</option>
                                      <option value="90d">3 tháng qua</option>
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <div className="pp-doc-filter-group">
                                  <label>Loại tài liệu</label>
                                  <div className="pp-doc-select-wrap">
                                    <select value={docCategory} onChange={e => { setDocCategory(e.target.value); setDocVisibleCount(8); }}>
                                      <option value="all">Tất cả</option>
                                      {DOC_CATEGORY_ORDER.map(id => (
                                        <option key={id} value={id}>{DOC_CATEGORY_META[id].label}</option>
                                      ))}
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <div className="pp-doc-filter-group">
                                  <label>Trạng thái</label>
                                  <div className="pp-doc-select-wrap">
                                    <select value={docStatus} onChange={e => { setDocStatus(e.target.value); setDocVisibleCount(8); }}>
                                      <option value="all">Tất cả</option>
                                      <option value="new">Mới tải lên (≤ 3 ngày)</option>
                                      <option value="archived">Đã lưu trữ</option>
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                </div>
                                <button className="pp-doc-reset-btn" onClick={resetFilters} disabled={!hasFiltersActive}>
                                  <RotateCcw size={13} /> Đặt lại bộ lọc
                                </button>
                              </div>
                            </div>

                            {/* Right: toolbar + grid/list */}
                            <div className="pp-doc-main">
                              <div className="pp-doc-toolbar">
                                <h3 className="pp-doc-toolbar-title">Tất cả tài liệu ({filtered.length})</h3>
                                <div className="pp-doc-toolbar-actions">
                                  <div className="pp-doc-search-wrap">
                                    <Search size={14} className="pp-doc-search-icon" />
                                    <input
                                      type="text"
                                      placeholder="Tìm kiếm theo tên tài liệu..."
                                      value={docSearch}
                                      onChange={e => { setDocSearch(e.target.value); setDocVisibleCount(8); }}
                                    />
                                  </div>
                                  <div className="pp-doc-select-wrap pp-doc-toolbar-select">
                                    <select value={docCategory} onChange={e => { setDocCategory(e.target.value); setDocVisibleCount(8); }} title="Loại tài liệu">
                                      <option value="all">Loại tài liệu</option>
                                      {DOC_CATEGORY_ORDER.map(id => (
                                        <option key={id} value={id}>{DOC_CATEGORY_META[id].label}</option>
                                      ))}
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                  <div className="pp-doc-select-wrap pp-doc-toolbar-select">
                                    <select value={docSort} onChange={e => setDocSort(e.target.value)} title="Sắp xếp">
                                      <option value="newest">Mới nhất</option>
                                      <option value="oldest">Cũ nhất</option>
                                      <option value="name">Tên A-Z</option>
                                      <option value="size">Dung lượng</option>
                                    </select>
                                    <ChevronDown size={14} className="pp-doc-select-chevron" />
                                  </div>
                                  <div className="pp-doc-view-toggle">
                                    <button className={docView === 'grid' ? 'active' : ''} onClick={() => setDocView('grid')} title="Xem dạng lưới">
                                      <LayoutGrid size={15} />
                                    </button>
                                    <button className={docView === 'list' ? 'active' : ''} onClick={() => setDocView('list')} title="Xem dạng danh sách">
                                      <List size={15} />
                                    </button>
                                  </div>
                                  <label className="pp-btn-add pp-btn-sm pp-upload-label">
                                    <Plus size={14} /> Thêm tài liệu
                                    <input type="file" hidden onChange={handleUploadAttachment} />
                                  </label>
                                </div>
                              </div>

                              {allAttachments.length === 0 ? (
                                <div className="pp-doc-empty">
                                  <div className="pp-doc-empty-icon"><FileText size={26} /></div>
                                  <h4>Chưa có tài liệu đính kèm nào</h4>
                                  <p>Tải lên kết quả xét nghiệm, hình ảnh chẩn đoán hoặc các tài liệu khác của bệnh nhân.</p>
                                  <label className="pp-btn-add pp-upload-label">
                                    <Plus size={16} /> Thêm tài liệu
                                    <input type="file" hidden onChange={handleUploadAttachment} />
                                  </label>
                                </div>
                              ) : filtered.length === 0 ? (
                                <div className="pp-doc-empty">
                                  <div className="pp-doc-empty-icon"><Search size={24} /></div>
                                  <h4>Không tìm thấy tài liệu</h4>
                                  <p>Không có tài liệu nào khớp với bộ lọc hiện tại.</p>
                                </div>
                              ) : (
                                <div className={docView === 'grid' ? 'pp-doc-grid' : 'pp-doc-list'}>
                                  {visible.map(docCard)}
                                </div>
                              )}

                              {visible.length < filtered.length && (
                                <button className="pp-doc-more-btn" onClick={() => setDocVisibleCount(c => c + 8)}>
                                  Xem thêm <ChevronDown size={14} />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {/* Ghi chú tab content */}
                      {patientProfileTab === 'notes' && (() => {
                        const notes = selectedPatient.notes || [];
                        const isCreatingBlankNote = isNoteFormOpen && !activeNoteId;
                        return (
                        <div className="pp-tp-wrap">
                          {/* Hidden while creating a new note or bulk-editing an existing one — only shown in the plain read-only view (and the empty state). */}
                          {!isNoteFormOpen && (
                            <div className="pp-tp-topbar">
                              <div className="pp-tp-visit-select">
                                <label>Chọn ghi chú</label>
                                <div className="pp-doc-select-wrap">
                                  <select
                                    value={activeNoteId || ''}
                                    onChange={e => selectNote(e.target.value)}
                                    disabled={!notes.length}
                                  >
                                    {!notes.length && <option value="">Chưa có ghi chú nào</option>}
                                    {notes.map(n => (
                                      <option key={n.id} value={n.id}>
                                        {formatDateVN(n.visit_date) || 'Chưa có ngày'} - {n.reason_for_visit || 'Ghi chú'}{n.status === 'draft' ? ' (Nháp)' : ''}
                                      </option>
                                    ))}
                                  </select>
                                  <ChevronDown size={14} className="pp-doc-select-chevron" />
                                </div>
                              </div>
                              <div className="pp-tp-topbar-actions">
                                <button className="pp-btn-add" onClick={openCreateNote}>
                                  <Plus size={14} /> Tạo ghi chú
                                </button>
                              </div>
                            </div>
                          )}

                          {!isCreatingBlankNote && !currentNote ? (
                            <div className="pp-card">
                              <div className="pp-empty-state">
                                <div className="pp-empty-icon"><ClipboardList size={26} /></div>
                                <h3>Chưa có ghi chú nào</h3>
                                <p>Tạo ghi chú thăm khám đầu tiên cho bệnh nhân để bắt đầu ghi nhận thông tin lâm sàng.</p>
                              </div>
                            </div>
                          ) : isNoteFormOpen ? (
                            <div className="pp-notes-page">
                              <div className="pp-notes-grid">
                                <div className="pp-notes-col">
                                  <div className="pp-form-group pp-notes-date-field">
                                    <label>Ngày khám <span className="pp-required">*</span></label>
                                    <input type="date" required value={noteFormDraft.visit_date} onChange={e => handleNoteFormFieldChange('visit_date', e.target.value)} />
                                  </div>

                                  <div className="pp-notes-field">
                                    <label>Lý do khám bệnh</label>
                                    <textarea
                                      rows={1}
                                      value={noteFormDraft.reason_for_visit}
                                      onChange={e => handleNoteFormFieldChange('reason_for_visit', e.target.value)}
                                      placeholder="Đau họng"
                                    />
                                  </div>

                                  <div className="pp-notes-field">
                                    <label>Dấu hiệu sinh tồn</label>
                                    <div className="pp-notes-vitals-row">
                                      {NOTES_VITALS_FIELDS.map(f => (
                                        <div className="pp-notes-vital" key={f.key}>
                                          <span className="pp-notes-vital-label">{f.label}</span>
                                          <div className="pp-notes-vital-input">
                                            <input
                                              type="text"
                                              value={noteFormDraft.vitals[f.key]}
                                              onChange={e => handleNoteFormVitalChange(f.key, e.target.value)}
                                              placeholder={f.placeholder}
                                            />
                                            <span className="pp-notes-vital-unit">{f.unit}</span>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>

                                  {NOTES_EXAM_FIELDS.map(f => (
                                    <div className="pp-notes-field" key={f.key}>
                                      <label>{f.label}</label>
                                      <textarea
                                        rows={2}
                                        value={noteFormDraft[f.key]}
                                        onChange={e => handleNoteFormFieldChange(f.key, e.target.value)}
                                        placeholder={f.placeholder}
                                      />
                                    </div>
                                  ))}
                                </div>

                                <div className="pp-notes-col">
                                  <div className="pp-notes-ent-card">
                                    <h4>Khám chuyên khoa Tai Mũi Họng</h4>
                                    {NOTES_ENT_FIELDS.map(f => (
                                      <div className="pp-notes-ent-field" key={f.key}>
                                        <label>{f.label}</label>
                                        <textarea
                                          rows={2}
                                          value={noteFormDraft[f.key]}
                                          onChange={e => handleNoteFormFieldChange(f.key, e.target.value)}
                                          placeholder={f.placeholder}
                                        />
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {(() => {
                                // Editing an already-finalized note (via "Sửa") never offers "Lưu nháp" —
                                // finalizing is one-way, so saving here just keeps status "final".
                                const editingFinal = !!activeNoteId && currentNote?.status === 'final';
                                return (
                                  <div className="pp-notes-footer">
                                    <button className="pp-btn-ghost" onClick={handleCancelNoteForm} disabled={isSavingNote}>Hủy</button>
                                    <div className="pp-notes-footer-right">
                                      {!editingFinal && (
                                        <button className="pp-btn-outline" onClick={handleSaveNoteDraft} disabled={isSavingNote}>Lưu nháp</button>
                                      )}
                                      <button className="pp-btn-add" onClick={handleSaveNoteFinal} disabled={isSavingNote}>{editingFinal ? 'Lưu' : 'Lưu ghi chú'}</button>
                                    </div>
                                  </div>
                                );
                              })()}
                            </div>
                          ) : (
                            <div className="pp-notes-page">
                              <div className="pp-tp-card-header">
                                <span className={`pp-status-badge ${NOTE_STATUS_META[currentNote.status]?.className || ''}`}>
                                  {NOTE_STATUS_META[currentNote.status]?.label || currentNote.status}
                                </span>
                                <div className="pp-tp-header-actions">
                                  <button className="pp-link-btn" onClick={() => openEditNote(currentNote)}><PencilLine size={12} /> Sửa</button>
                                  <button className="pp-icon-btn" title="Xóa ghi chú" onClick={() => handleDeleteNote(currentNote.id)}><Trash2 size={14} /></button>
                                </div>
                              </div>

                              <div className="pp-notes-grid">
                                <div className="pp-notes-col">
                                  {renderNoteReadField(currentNote, 'reason_for_visit', 'Lý do khám bệnh')}

                                  <div className="pp-tp-note-box">
                                    <div className="pp-tp-note-box-head">
                                      <span className="pp-tp-note-label">Dấu hiệu sinh tồn</span>
                                    </div>
                                    <p className="pp-tp-note-text">
                                      {NOTES_VITALS_FIELDS.map(f => currentNote.vitals[f.key] ? `${f.label}: ${currentNote.vitals[f.key]} ${f.unit}` : null).filter(Boolean).join('  •  ') || 'Chưa ghi nhận.'}
                                    </p>
                                  </div>

                                  {NOTES_EXAM_FIELDS.map(f => renderNoteReadField(currentNote, f.key, f.label))}
                                </div>

                                <div className="pp-notes-col">
                                  <div className="pp-notes-ent-card">
                                    <h4>Khám chuyên khoa Tai Mũi Họng</h4>
                                    {NOTES_ENT_FIELDS.map(f => renderNoteReadField(currentNote, f.key, f.label))}
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                        );
                      })()}

                    </div>

                    {/* Right sidebar */}
                    {patientProfileTab !== 'documents' && patientProfileTab !== 'notes' && patientProfileTab !== 'treatment' && (
                    <div className="pp-side">
                      {patientProfileTab === 'history' ? (() => {
                        const latestVisit = selectedPatient.visits[0] || null;
                        const goToTreatment = (visitId) => { setActiveTreatmentVisitId(visitId); setPatientProfileTab('treatment'); };
                        return (
                          <>
                            <div className="pp-card">
                              {!latestVisit ? (
                                <>
                                  <h3>Lần khám gần nhất</h3>
                                  <div className="pp-inline-empty">Chưa có lần khám nào.</div>
                                </>
                              ) : (() => {
                                const statusMeta = TREATMENT_STATUS_META[latestVisit.status] || TREATMENT_STATUS_META.completed;
                                return (
                                  <>
                                    <div className="pp-hist-side-header">
                                      <h3>Lần khám gần nhất</h3>
                                      <span className={`pp-status-badge ${statusMeta.className}`}>{statusMeta.label}</span>
                                    </div>
                                    <div className="pp-hist-side-date">
                                      {formatDateVN(latestVisit.visit_date)}{formatTimeVN(latestVisit.visit_date) && ` - ${formatTimeVN(latestVisit.visit_date)}`}
                                    </div>
                                    <div className="pp-hist-side-field">
                                      <div className="pp-hist-col-label">Chẩn đoán</div>
                                      <p className="pp-hist-side-value">{latestVisit.diagnosis_primary || 'Chưa có chẩn đoán.'}</p>
                                    </div>
                                    <div className="pp-hist-side-field">
                                      <div className="pp-hist-col-label">Bác sĩ điều trị</div>
                                      <p className="pp-hist-side-value">{latestVisit.doctor_name ? `BS. ${latestVisit.doctor_name}` : 'Chưa xác định'}</p>
                                    </div>
                                    <button className="pp-hist-side-btn" onClick={() => goToTreatment(latestVisit.id)}>
                                      Xem chi tiết kế hoạch điều trị <ChevronRight size={14} />
                                    </button>
                                  </>
                                );
                              })()}
                            </div>

                            <div className="pp-card">
                              <div className="pp-hist-side-header">
                                <h3>Tài liệu liên quan gần nhất</h3>
                                {(selectedPatient.attachments || []).length > 0 && (
                                  <button className="pp-link-btn" onClick={() => setPatientProfileTab('documents')}>Xem tất cả</button>
                                )}
                              </div>
                              {(selectedPatient.attachments || []).length === 0 ? (
                                <div className="pp-inline-empty">Chưa có tài liệu nào.</div>
                              ) : (
                                <div className="pp-attachment-list">
                                  {selectedPatient.attachments.slice(0, 3).map(att => (
                                    <div key={att.id} className="pp-attachment-item">
                                      <div className={`pp-doc-row-icon pp-doc-hue-${getDocFileHue(att.file_type)}`}>
                                        {['JPG', 'JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF'].includes((att.file_type || '').toUpperCase()) ? <ImageIcon size={15} /> : <FileText size={15} />}
                                      </div>
                                      <div className="pp-attachment-info">
                                        <div className="pp-attachment-name">{att.original_name}</div>
                                        <div className="pp-attachment-meta">{formatDateVN(att.uploaded_at)}</div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </>
                        );
                      })() : (
                      <>
                      {/* Quick note */}
                      <div className="pp-card pp-quicknote">
                        <div className="pp-quicknote-header">
                          <h3>Ghi chú nhanh</h3>
                          {!isEditingQuickNote && (
                            <button className="pp-link-btn" onClick={() => { setQuickNoteDraft(selectedPatient.quick_note || ''); setIsEditingQuickNote(true); }}>
                              <PencilLine size={12} /> Sửa
                            </button>
                          )}
                        </div>
                        {isEditingQuickNote ? (
                          <>
                            <textarea
                              className="pp-textarea"
                              rows={4}
                              value={quickNoteDraft}
                              onChange={(e) => setQuickNoteDraft(e.target.value)}
                              autoFocus
                            />
                            <div className="pp-quicknote-actions">
                              <button className="pp-btn-ghost" onClick={() => setIsEditingQuickNote(false)}>Hủy</button>
                              <button className="pp-btn-add pp-btn-sm" onClick={handleSaveQuickNote}>Lưu</button>
                            </div>
                          </>
                        ) : (
                          <>
                            <p className="pp-quicknote-text">{selectedPatient.quick_note || 'Chưa có ghi chú nhanh nào cho bệnh nhân này.'}</p>
                            {selectedPatient.quick_note_updated_at && (
                              <div className="pp-quicknote-footer">
                                Cập nhật: {formatDateVN(selectedPatient.quick_note_updated_at)} bởi {selectedPatient.quick_note_updated_by}
                              </div>
                            )}
                          </>
                        )}
                      </div>

                      {/* Medical alert */}
                      <div className={`pp-card pp-alert-card ${hasClinicalValue(selectedPatient.allergies) ? 'danger' : 'neutral'}`}>
                        <h3>Cảnh báo y tế</h3>
                        {/* Cùng một phép thử với bốn ô thông tin y tế: chuỗi
                            "Không có" nằm trong cơ sở dữ liệu là chỗ trống, không
                            phải một cảnh báo. */}
                        {hasClinicalValue(selectedPatient.allergies) ? (
                          <div className="pp-alert-box">
                            <AlertCircle size={16} />
                            <div>
                              <div className="pp-alert-title">Dị ứng thuốc</div>
                              <div className="pp-alert-text">{selectedPatient.allergies}</div>
                            </div>
                            <ChevronRight size={15} className="pp-alert-chevron" />
                          </div>
                        ) : (
                          <div className="pp-inline-empty">Không có cảnh báo y tế nào.</div>
                        )}
                      </div>

                      {/* Vitals */}
                      <div className="pp-card">
                        <div className="pp-quicknote-header">
                          <h3>Chỉ số cơ bản</h3>
                        </div>
                        <div className="pp-vitals-list">
                          {Object.entries(VITAL_META).map(([key, meta]) => {
                            const reading = selectedPatient.vitals.find(v => v.vital_type === key);
                            const Icon = meta.icon;
                            return (
                              <div key={key} className="pp-vital-row">
                                <div className="pp-vital-icon" style={{ color: meta.color, background: `${meta.color}1a` }}><Icon size={15} /></div>
                                <div className="pp-vital-info">
                                  <span className="pp-vital-label">{meta.label}</span>
                                  <span className="pp-vital-date">{reading ? formatDateVN(reading.recorded_at) : '--'}</span>
                                </div>
                                <span className="pp-vital-value">{reading ? `${reading.value}${meta.unit ? ` ${meta.unit}` : ''}` : '--'}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Attachments */}
                      <div className="pp-card">
                        <div className="pp-quicknote-header">
                          <h3>Tài liệu đính kèm</h3>
                          <label className="pp-link-btn pp-upload-label">
                            <Plus size={13} /> Thêm
                            <input type="file" hidden onChange={handleUploadAttachment} />
                          </label>
                        </div>
                        {selectedPatient.attachments.length === 0 ? (
                          <div className="pp-inline-empty">Chưa có tài liệu đính kèm nào.</div>
                        ) : (
                          <div className="pp-attachment-list">
                            {selectedPatient.attachments.slice(0, 3).map(att => (
                              <div key={att.id} className="pp-attachment-item">
                                <div className="pp-attachment-icon">{['JPG', 'PNG', 'JPEG'].includes(att.file_type) ? <ImageIcon size={16} /> : <FileText size={16} />}</div>
                                <div className="pp-attachment-info">
                                  <div className="pp-attachment-name">{att.original_name}</div>
                                  <div className="pp-attachment-meta">{formatDateVN(att.uploaded_at)} • {att.file_type} • {formatFileSize(att.size_bytes)}</div>
                                </div>
                                <button className="pp-icon-btn" onClick={() => handleDownloadAttachment(att)} title="Tải xuống"><Download size={15} /></button>
                              </div>
                            ))}
                          </div>
                        )}
                        {selectedPatient.attachments.length > 3 && (
                          <button className="pp-link-btn" onClick={() => setPatientProfileTab('documents')}>Xem tất cả tài liệu</button>
                        )}
                      </div>

                      {/* Delete patient */}
                      <button className="pp-delete-patient-btn" onClick={() => handleDeletePatient(selectedPatient.id)}>
                        <Trash2 size={13} /> Xóa hồ sơ bệnh nhân
                      </button>
                      </>
                      )}
                    </div>
                    )}
                  </div>

                  <div className="pp-footer-note">
                    <Info size={13} />
                    <span>Thông tin trong hồ sơ được bảo mật và chỉ phục vụ mục đích chăm sóc sức khỏe.</span>
                  </div>
                </>
              )}

              {/* Slide-over panel: Thêm bệnh nhân */}
              <Dialog.Root open={isAddPatientOpen} onOpenChange={setIsAddPatientOpen}>
                <Dialog.Portal>
                  <Dialog.Overlay className="pp-modal-overlay" />
                  <Dialog.Content className="pp-modal-panel">
                    <div className="pp-modal-header">
                      <div className="pp-modal-header-left">
                        <div className="pp-modal-header-icon"><UserRound size={18} /></div>
                        <div>
                          <Dialog.Title className="pp-modal-title">Thêm bệnh nhân</Dialog.Title>
                          <Dialog.Description className="pp-modal-subtitle">
                            Thêm mới bệnh nhân vào hệ thống để quản lý hồ sơ và theo dõi điều trị.
                          </Dialog.Description>
                        </div>
                      </div>
                      <Dialog.Close asChild>
                        <button className="pp-icon-btn" title="Đóng"><X size={18} /></button>
                      </Dialog.Close>
                    </div>

                    <div className="pp-modal-body">
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">1</span> Thông tin cá nhân</div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Họ và tên <span className="pp-required">*</span></label>
                            <input type="text" required value={newPatName} onChange={(e) => setNewPatName(e.target.value)} placeholder="Nhập họ và tên bệnh nhân" />
                          </div>
                          <div className="pp-form-group">
                            <label>Mã bệnh nhân (tự động)</label>
                            <input type="text" disabled value={nextPatientCode} />
                          </div>
                        </div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Giới tính <span className="pp-required">*</span></label>
                            <div className="pp-radio-row">
                              {['Nam', 'Nữ', 'Khác'].map(g => (
                                <label key={g} className="pp-radio-option">
                                  <input type="radio" name="pp-gender" checked={newPatGender === g} onChange={() => setNewPatGender(g)} /> {g}
                                </label>
                              ))}
                            </div>
                          </div>
                          <div className="pp-form-group">
                            <label>Nhóm máu</label>
                            <select value={newPatBloodType} onChange={(e) => setNewPatBloodType(e.target.value)}>
                              <option value="">Chọn nhóm máu</option>
                              {['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(bt => <option key={bt} value={bt}>{bt}</option>)}
                            </select>
                          </div>
                        </div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Số điện thoại</label>
                            <input type="tel" value={newPatPhone} onChange={(e) => setNewPatPhone(e.target.value)} placeholder="Nhập số điện thoại" />
                          </div>
                          <div className="pp-form-group">
                            <label>Email</label>
                            <input type="email" value={newPatEmail} onChange={(e) => setNewPatEmail(e.target.value)} placeholder="Nhập email (nếu có)" />
                          </div>
                        </div>
                        <div className="pp-form-group">
                          <label>Địa chỉ</label>
                          <input type="text" value={newPatAddress} onChange={(e) => setNewPatAddress(e.target.value)} placeholder="Nhập địa chỉ liên hệ" />
                        </div>
                      </div>

                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">2</span> Thông tin y tế cơ bản</div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Chiều cao (cm)</label>
                            <div className="pp-stepper">
                              <button type="button" onClick={() => setNewPatHeight(v => Math.max(0, (parseFloat(v) || 0) - 1))}><Minus size={14} /></button>
                              <input type="number" value={newPatHeight} onChange={(e) => setNewPatHeight(e.target.value)} />
                              <button type="button" onClick={() => setNewPatHeight(v => (parseFloat(v) || 0) + 1)}><Plus size={14} /></button>
                            </div>
                          </div>
                          <div className="pp-form-group">
                            <label>Cân nặng (kg)</label>
                            <div className="pp-stepper">
                              <button type="button" onClick={() => setNewPatWeight(v => Math.max(0, (parseFloat(v) || 0) - 1))}><Minus size={14} /></button>
                              <input type="number" value={newPatWeight} onChange={(e) => setNewPatWeight(e.target.value)} />
                              <button type="button" onClick={() => setNewPatWeight(v => (parseFloat(v) || 0) + 1)}><Plus size={14} /></button>
                            </div>
                          </div>
                        </div>
                        <div className="pp-form-group">
                          <label>Chẩn đoán</label>
                          <textarea rows={2} value={newPatDiagnosis} onChange={(e) => setNewPatDiagnosis(e.target.value)} placeholder="Ví dụ: Viêm dạ dày cấp, tăng huyết áp, ..." />
                        </div>
                        <div className="pp-form-group">
                          <label>Tiền sử bệnh</label>
                          <textarea rows={2} value={newPatMedHistory} onChange={(e) => setNewPatMedHistory(e.target.value)} placeholder="Ví dụ: Đái tháo đường (2019), cắt ruột thừa (2018), ..." />
                        </div>
                        <div className="pp-form-group">
                          <label>Tiền sử gia đình</label>
                          <textarea rows={2} value={newPatFamilyHistory} onChange={(e) => setNewPatFamilyHistory(e.target.value)} placeholder="Ví dụ: Bố tăng huyết áp, mẹ đái tháo đường type 2, ..." />
                        </div>
                      </div>

                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">3</span> Dị ứng &amp; Ghi chú (nếu có)</div>
                        <textarea rows={3} value={newPatAllergiesNotes} onChange={(e) => setNewPatAllergiesNotes(e.target.value)} placeholder="Ví dụ: Dị ứng Penicillin, hải sản. Ghi chú thêm về bệnh nhân..." />
                      </div>

                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">4</span> Điều trị ban đầu (nếu có)</div>

                        <div className="pp-visit-med-block">
                          <div className="pp-visit-med-header">
                            <label>Thuốc điều trị</label>
                            {!isAddingPatMedication && (
                              <button type="button" className="pp-link-btn" onClick={() => setIsAddingPatMedication(true)}>
                                <Plus size={12} /> Thêm thuốc
                              </button>
                            )}
                          </div>

                          {newPatMedications.length > 0 && (
                            <div className="pp-visit-med-list">
                              {newPatMedications.map((m, i) => (
                                <div key={i} className="pp-visit-med-item">
                                  <div className="pp-visit-med-item-info">
                                    <span className="pp-visit-med-item-name">{m.name}</span>
                                    <span className="pp-visit-med-item-meta">{[m.dosage, m.form, m.frequency].filter(Boolean).join(' · ') || 'Chưa có chi tiết'}</span>
                                  </div>
                                  <button type="button" className="pp-icon-btn" onClick={() => handleRemovePatMedication(i)} title="Xóa thuốc"><Trash2 size={14} /></button>
                                </div>
                              ))}
                            </div>
                          )}

                          {newPatMedications.length === 0 && !isAddingPatMedication && (
                            <div className="pp-inline-empty">Chưa có thuốc nào được kê.</div>
                          )}

                          {isAddingPatMedication && (
                            <div className="pp-tp-med-add-form">
                              <div className="pp-form-row">
                                <div className="pp-form-group"><label>Tên thuốc</label><input type="text" value={patMedDraft.name} onChange={e => setPatMedDraft(d => ({ ...d, name: e.target.value }))} placeholder="Ví dụ: Paracetamol 500mg" autoFocus /></div>
                                <div className="pp-form-group"><label>Liều dùng</label><input type="text" value={patMedDraft.dosage} onChange={e => setPatMedDraft(d => ({ ...d, dosage: e.target.value }))} placeholder="1 viên/lần" /></div>
                              </div>
                              <div className="pp-form-row">
                                <div className="pp-form-group"><label>Dạng bào chế</label><input type="text" value={patMedDraft.form} onChange={e => setPatMedDraft(d => ({ ...d, form: e.target.value }))} placeholder="Viên nén" /></div>
                                <div className="pp-form-group"><label>Thời gian</label><input type="text" value={patMedDraft.frequency} onChange={e => setPatMedDraft(d => ({ ...d, frequency: e.target.value }))} placeholder="3 lần/ngày" /></div>
                              </div>
                              <div className="pp-form-group"><label>Hướng dẫn</label><textarea rows={2} value={patMedDraft.instructions} onChange={e => setPatMedDraft(d => ({ ...d, instructions: e.target.value }))} placeholder={'Sau ăn\nKhi sốt > 38.5°C'} /></div>
                              <div className="pp-tp-edit-actions">
                                <button type="button" className="pp-btn-ghost" onClick={() => { setIsAddingPatMedication(false); setPatMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '' }); }}>Hủy</button>
                                <button type="button" className="pp-btn-add pp-btn-sm" onClick={handleAddPatMedication} disabled={!patMedDraft.name.trim()}>Thêm thuốc</button>
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="pp-form-group">
                          <label>Khuyến nghị không dùng thuốc</label>
                          <textarea rows={2} value={newPatNoDrugRecommendations} onChange={(e) => setNewPatNoDrugRecommendations(e.target.value)} placeholder={'Không tự ý dùng kháng sinh khi chưa có chỉ định.\nHạn chế thuốc lá, rượu bia, đồ uống lạnh.'} />
                        </div>
                        <div className="pp-form-group">
                          <label>Hướng dẫn chăm sóc</label>
                          <textarea rows={3} value={newPatCareInstructions} onChange={(e) => setNewPatCareInstructions(e.target.value)} placeholder={'Uống nhiều nước ấm.\nNghỉ ngơi hợp lý, tránh thức khuya.'} />
                        </div>
                      </div>
                    </div>

                    <div className="pp-modal-footer">
                      <Dialog.Close asChild>
                        <button type="button" className="pp-btn-ghost">Hủy</button>
                      </Dialog.Close>
                      <button type="button" className="pp-btn-add" disabled={isSavingPatient || !newPatName.trim()} onClick={handleAddPatient}>
                        {isSavingPatient ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} Lưu bệnh nhân
                      </button>
                    </div>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>

              {/* Slide-over panel: Tạo kế hoạch mới (creates the underlying visit record) */}
              <Dialog.Root open={isAddVisitOpen} onOpenChange={setIsAddVisitOpen}>
                <Dialog.Portal>
                  <Dialog.Overlay className="pp-modal-overlay" />
                  <Dialog.Content className="pp-modal-panel">
                    <div className="pp-modal-header">
                      <div className="pp-modal-header-left">
                        <div className="pp-modal-header-icon"><Stethoscope size={18} /></div>
                        <div>
                          <Dialog.Title className="pp-modal-title">Tạo kế hoạch mới</Dialog.Title>
                          <Dialog.Description className="pp-modal-subtitle">
                            Ghi nhận thông tin lần khám mới cho {selectedPatient?.name || 'bệnh nhân'}.
                          </Dialog.Description>
                        </div>
                      </div>
                      <Dialog.Close asChild>
                        <button className="pp-icon-btn" title="Đóng"><X size={18} /></button>
                      </Dialog.Close>
                    </div>

                    <div className="pp-modal-body">
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title">Thông tin lần khám</div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Ngày khám <span className="pp-required">*</span></label>
                            <input type="date" required value={newVisitDate} onChange={(e) => setNewVisitDate(e.target.value)} />
                          </div>
                          <div className="pp-form-group">
                            <label>Bác sĩ khám</label>
                            <input type="text" value={newVisitDoctor} onChange={(e) => setNewVisitDoctor(e.target.value)} placeholder="Nhập tên bác sĩ" />
                          </div>
                        </div>
                        <div className="pp-form-group">
                          <label>Tiêu đề lần khám</label>
                          <input type="text" value={newVisitTitle} onChange={(e) => setNewVisitTitle(e.target.value)} placeholder="Ví dụ: Khám tổng quát, Tái khám viêm họng, ..." />
                        </div>
                      </div>

                      {/* 1. Chẩn đoán */}
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">1</span> Chẩn đoán</div>

                        <div className="pp-form-group">
                          <label>Triệu chứng</label>
                          <input
                            type="text"
                            value={newVisitSymptomInput}
                            onChange={(e) => setNewVisitSymptomInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddVisitSymptom(); } }}
                            placeholder="Ví dụ: sốt nhẹ 37.8 độ C, đau họng khi nuốt, ho khan..."
                          />
                        </div>
                        <button type="button" className="pp-btn-add-symptom" onClick={handleAddVisitSymptom} disabled={!newVisitSymptomInput.trim()}>
                          <Plus size={14} /> Triệu chứng
                        </button>
                        {newVisitSymptoms.length > 0 && (
                          <div className="pp-symptom-tags">
                            {newVisitSymptoms.map((s, i) => (
                              <span key={i} className="pp-symptom-tag">
                                {s}
                                <button type="button" onClick={() => handleRemoveVisitSymptom(i)} title="Xóa triệu chứng"><X size={12} /></button>
                              </span>
                            ))}
                          </div>
                        )}

                        <div className="pp-form-group">
                          <label>Chẩn đoán chính</label>
                          <input type="text" value={newVisitDiagnosis} onChange={(e) => setNewVisitDiagnosis(e.target.value)} placeholder="Ví dụ: Viêm họng cấp do virus (J02.9)" />
                        </div>
                        <div className="pp-form-group">
                          <label>Chẩn đoán phân biệt (mỗi dòng một chẩn đoán)</label>
                          <textarea rows={3} value={newVisitDiagnosisSecondary} onChange={(e) => setNewVisitDiagnosisSecondary(e.target.value)} placeholder={'Viêm họng do liên cầu khuẩn (J02.0)\nViêm amidan cấp (J03.9)'} />
                        </div>
                        <div className="pp-form-group">
                          <label>Khám lâm sàng</label>
                          <textarea rows={3} value={newVisitExamFindings} onChange={(e) => setNewVisitExamFindings(e.target.value)} placeholder="Niêm mạc họng viêm, không có mủ, không hạch cổ to." />
                        </div>
                      </div>

                      {/* 2. Kế hoạch điều trị */}
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">2</span> Kế hoạch điều trị</div>

                        <div className="pp-form-group">
                          <label>Mục tiêu điều trị (mỗi dòng một mục tiêu)</label>
                          <textarea rows={3} value={newVisitGoals} onChange={(e) => setNewVisitGoals(e.target.value)} placeholder={'Giảm nhanh triệu chứng\nNgăn ngừa biến chứng'} />
                        </div>
                        <div className="pp-form-row">
                          <div className="pp-form-group">
                            <label>Phương pháp điều trị</label>
                            <input type="text" value={newVisitTreatmentMethod} onChange={(e) => setNewVisitTreatmentMethod(e.target.value)} placeholder="Nội khoa" />
                          </div>
                          <div className="pp-form-group">
                            <label>Thời gian dự kiến</label>
                            <input type="text" value={newVisitProtocolDuration} onChange={(e) => setNewVisitProtocolDuration(e.target.value)} placeholder="5 - 7 ngày" />
                          </div>
                        </div>
                        <div className="pp-form-group">
                          <label>Chế độ</label>
                          <textarea rows={2} value={newVisitDietRegimen} onChange={(e) => setNewVisitDietRegimen(e.target.value)} placeholder="Nghỉ ngơi, uống nhiều nước ấm, ăn thức ăn mềm, dễ nuốt." />
                        </div>
                        <div className="pp-form-group">
                          <label>Lưu ý</label>
                          <textarea rows={2} value={newVisitPrecautions} onChange={(e) => setNewVisitPrecautions(e.target.value)} placeholder="Tránh khói bụi, không hút thuốc lá, không uống rượu bia." />
                        </div>
                        <div className="pp-form-group">
                          <label>Mục đích / tiêu chí tái khám</label>
                          <textarea rows={2} value={newVisitFollowupPurpose} onChange={(e) => setNewVisitFollowupPurpose(e.target.value)} placeholder="Nếu không cải thiện sau 3 ngày hoặc nặng hơn." />
                        </div>
                        <div className="pp-form-group">
                          <label>Ngày hẹn tái khám (nếu có)</label>
                          <input type="date" value={newVisitFollowupDate} onChange={(e) => setNewVisitFollowupDate(e.target.value)} />
                        </div>
                        <div className="pp-form-group">
                          <label>Ghi chú điều trị (nếu có)</label>
                          <textarea rows={2} value={newVisitTreatmentInstructions} onChange={(e) => setNewVisitTreatmentInstructions(e.target.value)} placeholder="Nhập ghi chú thêm về hướng điều trị..." />
                        </div>
                      </div>

                      {/* 3. Đơn thuốc */}
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">3</span> Đơn thuốc</div>

                        <div className="pp-visit-med-block">
                          <div className="pp-visit-med-header">
                            <label>Thuốc kê đơn</label>
                            {!isAddingVisitMedication && (
                              <button type="button" className="pp-link-btn" onClick={() => setIsAddingVisitMedication(true)}>
                                <Plus size={12} /> Thêm thuốc
                              </button>
                            )}
                          </div>

                          {newVisitMedications.length > 0 && (
                            <div className="pp-visit-med-list">
                              {newVisitMedications.map((m, i) => (
                                <div key={i} className="pp-visit-med-item">
                                  <div className="pp-visit-med-item-info">
                                    <span className="pp-visit-med-item-name">{m.name}</span>
                                    <span className="pp-visit-med-item-meta">{[m.dosage, m.form, m.frequency, m.quantity && `SL: ${m.quantity}`].filter(Boolean).join(' · ') || 'Chưa có chi tiết'}</span>
                                  </div>
                                  <button type="button" className="pp-icon-btn" onClick={() => handleRemoveVisitMedication(i)} title="Xóa thuốc"><Trash2 size={14} /></button>
                                </div>
                              ))}
                            </div>
                          )}

                          {newVisitMedications.length === 0 && !isAddingVisitMedication && (
                            <div className="pp-inline-empty">Chưa có thuốc nào được kê.</div>
                          )}

                          {isAddingVisitMedication && (
                            <div className="pp-tp-med-add-form">
                              <div className="pp-form-row">
                                <div className="pp-form-group"><label>Tên thuốc</label><input type="text" value={visitMedDraft.name} onChange={e => setVisitMedDraft(d => ({ ...d, name: e.target.value }))} placeholder="Ví dụ: Paracetamol 500mg" autoFocus /></div>
                                <div className="pp-form-group"><label>Dạng bào chế</label><input type="text" value={visitMedDraft.form} onChange={e => setVisitMedDraft(d => ({ ...d, form: e.target.value }))} placeholder="Viên nén" /></div>
                              </div>
                              <div className="pp-form-row">
                                <div className="pp-form-group"><label>Liều dùng</label><input type="text" value={visitMedDraft.dosage} onChange={e => setVisitMedDraft(d => ({ ...d, dosage: e.target.value }))} placeholder="1 viên/lần" /></div>
                                <div className="pp-form-group"><label>Thời gian</label><input type="text" value={visitMedDraft.frequency} onChange={e => setVisitMedDraft(d => ({ ...d, frequency: e.target.value }))} placeholder="3 lần/ngày" /></div>
                              </div>
                              <div className="pp-form-row">
                                <div className="pp-form-group"><label>Số lượng</label><input type="text" value={visitMedDraft.quantity} onChange={e => setVisitMedDraft(d => ({ ...d, quantity: e.target.value }))} placeholder="10 viên" /></div>
                                <div className="pp-form-group"><label>Hướng dẫn</label><input type="text" value={visitMedDraft.instructions} onChange={e => setVisitMedDraft(d => ({ ...d, instructions: e.target.value }))} placeholder="Sau ăn" /></div>
                              </div>
                              <div className="pp-tp-edit-actions">
                                <button type="button" className="pp-btn-ghost" onClick={() => { setIsAddingVisitMedication(false); setVisitMedDraft({ name: '', dosage: '', form: '', frequency: '', instructions: '', quantity: '' }); }}>Hủy</button>
                                <button type="button" className="pp-btn-add pp-btn-sm" onClick={handleAddVisitMedication} disabled={!visitMedDraft.name.trim()}>Thêm thuốc</button>
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="pp-form-group">
                          <label>Lưu ý (không dùng thuốc)</label>
                          <textarea rows={2} value={newVisitNoDrugRecommendations} onChange={(e) => setNewVisitNoDrugRecommendations(e.target.value)} placeholder={'Không tự ý dùng kháng sinh khi chưa có chỉ định.\nHạn chế thuốc lá, rượu bia, đồ uống lạnh.'} />
                        </div>
                      </div>

                      {/* 4. Hướng dẫn cho bệnh nhân */}
                      <div className="pp-modal-section">
                        <div className="pp-modal-section-title"><span className="pp-section-badge">4</span> Hướng dẫn cho bệnh nhân</div>
                        <div className="pp-form-group">
                          <textarea rows={3} value={newVisitCareInstructions} onChange={(e) => setNewVisitCareInstructions(e.target.value)} placeholder={'Uống nhiều nước ấm.\nNghỉ ngơi hợp lý, tránh thức khuya.'} />
                        </div>
                      </div>
                    </div>

                    <div className="pp-modal-footer">
                      <Dialog.Close asChild>
                        <button type="button" className="pp-btn-ghost">Hủy</button>
                      </Dialog.Close>
                      <button type="button" className="pp-btn-add" disabled={isSavingVisit || !newVisitDate || patientDetailLoading} onClick={handleSaveNewVisit}>
                        {(isSavingVisit || patientDetailLoading) ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} Lưu lần khám
                      </button>
                    </div>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </div>
          )}

          {/* TAB 5: Diagnosis Tree (Sơ đồ chẩn đoán tương tác) */}
          {activeTab === 'stats' && (
            <DashboardView permissions={permissions} />
          )}

          {activeTab === 'reminders' && (
            <RemindersView
              permissions={permissions}
              patients={patients}
              onOpenPatient={(patientId) => { handleSelectSearchedPatient(patientId); }}
              onChanged={fetchNotifications}
            />
          )}

          {activeTab === 'diagnosisTree' && (
            <DiagnosisTreeView
              centerTreeCanvas={centerTreeCanvas}
              collectSymptoms={collectSymptoms}
              diagPatientQuery={diagPatientQuery}
              diagPatientResults={diagPatientResults}
              diagPatientSearchOpen={diagPatientSearchOpen}
              diagSelectedPatient={diagSelectedPatient}
              examLoading={examLoading}
              examNotes={examNotes}
              examResult={examResult}
              finalDiagnoses={finalDiagnoses}
              finalLoading={finalLoading}
              handleDiagPatientSearchChange={handleDiagPatientSearchChange}
              handleFinalDiagnosis={handleFinalDiagnosis}
              handleGenerateTree={handleGenerateTree}
              handleSelectDiagPatient={handleSelectDiagPatient}
              handleSuggestExam={handleSuggestExam}
              handleToggleDiagnosisSelected={handleToggleDiagnosisSelected}
              handleTreeCanvasMouseDown={handleTreeCanvasMouseDown}
              handleUpdateDisease={handleUpdateDisease}
              isPanningTree={isPanningTree}
              isPreparingHandoff={isPreparingHandoff}
              nodeStatusMap={nodeStatusMap}
              patientDesc={patientDesc}
              renderDecisionTreeNode={renderDecisionTreeNode}
              selectedDiagnosisDetail={selectedDiagnosisDetail}
              selectedDiagnosisIds={selectedDiagnosisIds}
              setDiagPatientSearchOpen={setDiagPatientSearchOpen}
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

          {/* TAB 6: Giới thiệu */}
          {activeTab === 'about' && (
            <IntroExperience onExit={() => setActiveTab('chat')} />
          )}

        </div>

        {/* Universal Footer Banner — toggled by Settings → An toàn */}
        {settings.showDisclaimer && (
          <footer className="workspace-footer-bar">
            <span>Thông tin chỉ mang tính chất tham khảo lâm sàng học thuật, quyết định điều trị cuối cùng thuộc về bác sĩ chuyên môn.</span>
          </footer>
        )}
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
          patientCount: patients.length,
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
