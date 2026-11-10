import { Activity, Baby, Bone, Brain, Droplets, Ear, HeartPulse, Microscope, ScanFace, ShieldPlus, Stethoscope, Wind } from 'lucide-react';
import { foldWithMap } from './fold';

export const specialties = [
  { id: 'tim-mach', name: 'Tim mạch', english: 'Cardiology', description: 'Tim, mạch máu và sức khỏe tuần hoàn.', Icon: HeartPulse, color: 'rose', cover: '/notebooks/tim-mach.webp' },
  { id: 'tai-mui-hong', name: 'Tai mũi họng', english: 'Otolaryngology', description: 'Thính giác, mũi xoang và vùng họng.', Icon: Ear, color: 'mint', cover: '/notebooks/tai-mui-hong.webp' },
  { id: 'ho-hap', name: 'Hô hấp', english: 'Pulmonology', description: 'Phổi, đường thở và chức năng hô hấp.', Icon: Wind, color: 'blue', cover: '/notebooks/ho-hap.webp' },
  { id: 'than-kinh', name: 'Thần kinh', english: 'Neurology', description: 'Não bộ, tủy sống và hệ thần kinh.', Icon: Brain, color: 'lavender', cover: '/notebooks/than-kinh.webp' },
  { id: 'noi-tiet', name: 'Nội tiết', english: 'Endocrinology', description: 'Hormon, chuyển hóa và các tuyến nội tiết.', Icon: Activity, color: 'peach', cover: '/notebooks/noi-tiet.webp' },
  { id: 'tieu-hoa', name: 'Tiêu hóa', english: 'Gastroenterology', description: 'Hệ tiêu hóa, gan, mật và tụy.', Icon: Stethoscope, color: 'sand', cover: '/notebooks/tieu-hoa.webp' },
  { id: 'than-tiet-nieu', name: 'Thận – Tiết niệu', english: 'Nephrology · Urology', description: 'Thận, cân bằng dịch và đường tiết niệu.', Icon: Droplets, color: 'blue', cover: '/notebooks/than-tiet-nieu.webp' },
  { id: 'nhi-khoa', name: 'Nhi khoa', english: 'Pediatrics', description: 'Sức khỏe và sự phát triển của trẻ em.', Icon: Baby, color: 'peach', cover: '/notebooks/nhi-khoa.webp' },
  { id: 'co-xuong-khop', name: 'Cơ xương khớp', english: 'Musculoskeletal medicine', description: 'Cơ, xương, khớp và hệ vận động.', Icon: Bone, color: 'mint', cover: '/notebooks/co-xuong-khop.webp' },
  { id: 'da-lieu', name: 'Da liễu', english: 'Dermatology', description: 'Da, tóc, móng và các vấn đề liên quan.', Icon: ScanFace, color: 'rose', cover: '/notebooks/da-lieu.webp' },
  { id: 'truyen-nhiem', name: 'Truyền nhiễm', english: 'Infectious diseases', description: 'Bệnh truyền nhiễm và tác nhân gây bệnh.', Icon: Microscope, color: 'sand', cover: '/notebooks/truyen-nhiem.webp' },
  { id: 'san-phu-khoa', name: 'Sản – Phụ khoa', english: 'Obstetrics · Gynecology', description: 'Sức khỏe sinh sản và chăm sóc thai kỳ.', Icon: ShieldPlus, color: 'lavender', cover: '/notebooks/san-phu-khoa.webp' },
];

export const specialtyHref = specialty => `/hoi-dap?${new URLSearchParams({ 'chuyen-khoa': specialty.id })}`;

export function matchingSpecialties(query) {
  const term = foldWithMap(query).folded;
  return specialties.filter(item => foldWithMap(`${item.name} ${item.english} ${item.description}`).folded.includes(term));
}
