import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, useScroll, useTransform } from 'motion/react';
import Lenis from 'lenis';
import {
  X,
  ChevronDown,
  MessageSquare,
  Pill,
  Library,
  Users,
  GitBranch,
  Mic,
  Search,
  FileText,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';
import './IntroExperience.css';

// Drop generated background art into frontend/public/intro-bg/ using these exact
// filenames — the CSS background-image simply fails silently (falls back to the
// plain dark theme) until each file exists, so this works before and after.
// The optional .mp4 next to each .jpg is an animated loop layered on top; the jpg
// stays as-is underneath as the fallback if the video is missing or fails to load.
//
// trans-<from>-<to>.mp4 are short (~2s) generated clips that morph one section's
// background into the next. They're optional too: if missing, the crossfade
// between the two backgrounds' own opacity curves still reads as one continuous
// world, just without the extra "morph" motion.
const HERO_BACKGROUNDS = ['/intro-bg/hero-1.jpg', '/intro-bg/hero-2.jpg', '/intro-bg/hero-3.jpg'];
const HERO_CHOICE_INDEX = 0; // swap to 1 or 2 once a variant is picked
const HERO_VIDEO = '/intro-bg/hero-1.mp4';

const SECTIONS = [
  {
    id: 'chat',
    eyebrow: '01 · TRÒ CHUYỆN',
    title: 'Hỏi đáp lâm sàng, luôn kèm nguồn trích dẫn',
    body: 'Gõ câu hỏi hoặc bấm biểu tượng micro để nói thay vì gõ. Mỗi câu trả lời đi kèm bảng "Nguồn" — bấm vào để đọc nguyên trang tài liệu, giống NotebookLM.',
    icon: MessageSquare,
    mock: ChatMock,
    bg: '/intro-bg/bg-chat.jpg',
    video: '/intro-bg/bg-chat.mp4',
  },
  {
    id: 'medicine',
    eyebrow: '02 · TRA CỨU THUỐC',
    title: 'Tra cứu thuốc & triệu chứng tức thì',
    body: 'Kết quả lấy thẳng từ y văn đã chỉ mục, không qua AI tổng hợp câu trả lời — chính xác từng câu chữ, có trang nguồn đi kèm.',
    icon: Pill,
    mock: MedicineMock,
    bg: '/intro-bg/bg-medicine.jpg',
    video: '/intro-bg/bg-medicine.mp4',
  },
  {
    id: 'library',
    eyebrow: '03 · THƯ VIỆN',
    title: 'Nền tảng tài liệu cho mọi câu trả lời',
    body: 'Tải lên file PDF để nhập vào hệ thống và quản lý tài liệu đã được chỉ mục — đây là kho kiến thức đứng sau mọi câu trả lời của Trợ lý FII.',
    icon: Library,
    mock: LibraryMock,
    bg: '/intro-bg/bg-library.jpg',
    video: '/intro-bg/bg-library.mp4',
  },
  {
    id: 'patients',
    eyebrow: '04 · BỆNH NHÂN',
    title: 'Hồ sơ bệnh nhân, gọn trong một nơi',
    body: 'Lưu thông tin và lịch sử khám của từng bệnh nhân, sẵn sàng tra lại bất cứ lúc nào cho lần chẩn đoán tiếp theo.',
    icon: Users,
    mock: PatientMock,
    bg: '/intro-bg/bg-patients.jpg',
    video: '/intro-bg/bg-patients.mp4',
  },
  {
    id: 'diagnosisTree',
    eyebrow: '05 · CHẨN ĐOÁN',
    title: 'Cây chẩn đoán, từng bước một',
    body: 'Nhập mô tả bệnh nhân và ấn "Tạo cây chẩn đoán", chọn Có/Không trên cây, ấn "Gợi ý khám & nội soi", nhập kết quả khám thực tế rồi ấn "Tiến hành chẩn đoán cuối cùng".',
    icon: GitBranch,
    mock: DiagnosisMock,
    bg: '/intro-bg/bg-diagnosis.jpg',
    video: '/intro-bg/bg-diagnosis.mp4',
  },
];

// One persistent "world" — hero plus every feature section's background, stacked
// in a fixed full-viewport layer behind the scrolling content and crossfaded by
// each layer's own scroll progress. See BackgroundStack/WorldLayer below.
const WORLD_LAYERS = [
  { id: 'hero', bg: HERO_BACKGROUNDS[HERO_CHOICE_INDEX], video: HERO_VIDEO, baseOpacity: 0.7 },
  ...SECTIONS.map((s) => ({ id: s.id, bg: s.bg, video: s.video, baseOpacity: 0.55 })),
];

// Boundary k connects WORLD_LAYERS[k] -> WORLD_LAYERS[k+1] (hero=0, chat=1, ...).
// Only plays on forward, adjacent scroll (skips on dot-nav jumps or scrolling back
// up, since <video> can't play in reverse) — the crossfade alone still connects
// those cases.
const TRANSITIONS = [
  { src: '/intro-bg/trans-hero-chat.mp4' },
  { src: '/intro-bg/trans-chat-medicine.mp4' },
  { src: '/intro-bg/trans-medicine-library.mp4' },
  { src: '/intro-bg/trans-library-patients.mp4' },
  { src: '/intro-bg/trans-patients-diagnosis.mp4' },
];

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches
  );
  useEffect(() => {
    const mql = window.matchMedia('(max-width: 900px)');
    const handler = (e) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  return isMobile;
}

export default function IntroExperience({ onExit }) {
  const scrollRef = useRef(null);
  const contentRef = useRef(null);
  const heroRef = useRef(null);
  const sectionRefs = useMemo(() => SECTIONS.map(() => ({ current: null })), []);
  const layerRefs = useMemo(() => [heroRef, ...sectionRefs], [sectionRefs]);
  const prevActiveRef = useRef(-1);

  const [activeIndex, setActiveIndex] = useState(-1);
  const [activeTransition, setActiveTransition] = useState(null);
  const { scrollYProgress } = useScroll({ container: scrollRef });

  const handleTransitionDone = useCallback(() => setActiveTransition(null), []);

  useEffect(() => {
    if (!scrollRef.current || !contentRef.current) return undefined;

    const lenis = new Lenis({
      wrapper: scrollRef.current,
      content: contentRef.current,
      duration: 1.15,
      smoothWheel: true,
    });

    let rafId;
    function raf(time) {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    }
    rafId = requestAnimationFrame(raf);

    return () => {
      cancelAnimationFrame(rafId);
      lenis.destroy();
    };
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const idx = Number(entry.target.dataset.sectionIndex);
          const prevIdx = prevActiveRef.current;
          if (prevIdx === idx) return;

          const prevLayer = prevIdx + 1;
          const nextLayer = idx + 1;
          if (nextLayer - prevLayer === 1 && TRANSITIONS[prevLayer]) {
            setActiveTransition({ src: TRANSITIONS[prevLayer].src, key: prevLayer });
          }
          prevActiveRef.current = idx;
          setActiveIndex(idx);
        });
      },
      { root: container, threshold: 0.5 }
    );

    const nodes = container.querySelectorAll('[data-section-index]');
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="intro-experience">
      <BackgroundStack layers={WORLD_LAYERS} refs={layerRefs} scrollRef={scrollRef} />
      <TransitionVideoLayer transition={activeTransition} onDone={handleTransitionDone} />
      <AtmosphereLayer />

      <div className="intro-progress-track">
        <motion.div className="intro-progress-fill" style={{ scaleX: scrollYProgress }} />
      </div>

      <button type="button" className="intro-exit-btn" onClick={onExit} title="Đóng, quay lại ứng dụng">
        <X size={18} />
      </button>

      <nav className="intro-dot-nav">
        {SECTIONS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            className={`intro-dot${activeIndex === i ? ' active' : ''}`}
            title={s.eyebrow}
            onClick={() => {
              const node = scrollRef.current?.querySelector(`[data-section-index="${i}"]`);
              node?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          />
        ))}
      </nav>

      <div className="intro-scroll-viewport" ref={scrollRef}>
        <div className="intro-scroll-content" ref={contentRef}>
          <HeroSection scrollRef={scrollRef} heroRef={heroRef} />

          {SECTIONS.map((section, i) => (
            <FeatureSection
              key={section.id}
              index={i}
              section={section}
              scrollRef={scrollRef}
              sectionRef={sectionRefs[i]}
            />
          ))}

          <ClosingSection onExit={onExit} />
        </div>
      </div>
    </div>
  );
}

// --- One continuous world: fixed, full-viewport background layers crossfaded by
// each section's own scroll progress, so adjacent layers overlap instead of
// cutting to black at the section boundary. ---

function BackgroundStack({ layers, refs, scrollRef }) {
  return (
    <div className="intro-world-stack">
      {layers.map((layer, i) => (
        <WorldLayer key={layer.id} layer={layer} targetRef={refs[i]} scrollRef={scrollRef} z={i + 1} />
      ))}
    </div>
  );
}

function WorldLayer({ layer, targetRef, scrollRef, z }) {
  const isMobile = useIsMobile();
  const { scrollYProgress } = useScroll({
    target: targetRef,
    container: scrollRef,
    offset: ['start end', 'end start'],
  });
  const opacity = useTransform(scrollYProgress, [0, 0.22, 0.78, 1], [0, 1, 1, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [1, isMobile ? 1.05 : 1.12]);
  const y = useTransform(scrollYProgress, [0, 1], isMobile ? ['-3%', '3%'] : ['-6%', '6%']);

  return (
    <motion.div className="world-layer" style={{ opacity, zIndex: z }}>
      <motion.div
        className="world-layer-image"
        style={{ backgroundImage: `url(${layer.bg})`, scale, y, opacity: layer.baseOpacity }}
      />
      <BgVideo src={layer.video} className="world-layer-video" style={{ opacity: layer.baseOpacity }} />
    </motion.div>
  );
}

// Plays the boundary's morph clip once on forward entry, then hides itself; falls
// back to nothing (pure crossfade) if the file is missing, errors out, or never
// becomes playable in time. The ~2.2s on-screen window is measured from when
// playback actually starts (not from mount) so a clip that takes a moment to
// buffer still gets shown instead of being yanked before its first frame; a
// longer bail-out timer is the safety net for a file that never plays at all.
// Clips longer than ~2.2s (the source video's own length doesn't matter) are
// simply cut short here, keeping the "bridge" moment brisk.
function TransitionVideoLayer({ transition, onDone }) {
  const videoRef = useRef(null);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !transition) return undefined;

    let cutoffTimer = null;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(cutoffTimer);
      clearTimeout(bailTimer);
      onDone();
    };
    const handlePlaying = () => {
      clearTimeout(bailTimer);
      cutoffTimer = setTimeout(finish, 2200);
    };

    el.currentTime = 0;
    el.addEventListener('playing', handlePlaying);
    const playPromise = el.play();
    if (playPromise?.catch) playPromise.catch(() => {});

    const bailTimer = setTimeout(finish, 4500);

    return () => {
      el.removeEventListener('playing', handlePlaying);
      clearTimeout(cutoffTimer);
      clearTimeout(bailTimer);
    };
  }, [transition, onDone]);

  if (!transition) return null;

  return (
    <video
      ref={videoRef}
      className="intro-transition-video active"
      src={transition.src}
      muted
      playsInline
      preload="auto"
      onEnded={onDone}
      onError={onDone}
    />
  );
}

// Fixed vignette + drifting light dust that never unmounts between sections —
// the constant thread that ties every background into one atmosphere.
function AtmosphereLayer() {
  const particles = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => ({
        id: i,
        top: `${(i * 37) % 100}%`,
        left: `${(i * 53) % 100}%`,
        size: 2 + ((i * 7) % 5),
        duration: 10 + ((i * 3) % 12),
        delay: -(i * 1.7),
        opacity: 0.25 + ((i % 4) * 0.08),
        dx: ((i % 5) - 2) * 10,
        dy: ((i % 7) - 3) * 12,
      })),
    []
  );

  return (
    <div className="intro-atmosphere">
      <div className="intro-atmosphere-vignette" />
      <div className="intro-atmosphere-particles">
        {particles.map((p) => (
          <span
            key={p.id}
            className="intro-atmosphere-particle"
            style={{
              top: p.top,
              left: p.left,
              width: p.size,
              height: p.size,
              '--p-op': p.opacity,
              '--p-dx': `${p.dx}px`,
              '--p-dy': `${p.dy}px`,
              animationDuration: `${p.duration}s`,
              animationDelay: `${p.delay}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// --- Text reveal: heading solidifies from an outline into a filled color once
// on first entry; body copy fades/blurs in word by word. ---

function RevealHeading({ as = 'h2', className = '', color = '#f5f7fa', strokeColor = 'rgba(148,163,184,0.45)', children }) {
  const MotionTag = motion[as];
  return (
    <MotionTag
      className={className}
      style={{ WebkitTextStroke: `1px ${strokeColor}` }}
      initial={{ color: 'rgba(245,247,250,0)' }}
      whileInView={{ color }}
      viewport={{ once: true, amount: 0.6 }}
      transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </MotionTag>
  );
}

function RevealBody({ as = 'p', className = '', children }) {
  const words = useMemo(() => String(children).split(' '), [children]);
  const Tag = as;
  return (
    <Tag className={className}>
      <motion.span
        className="reveal-body-inner"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.5 }}
        variants={{ visible: { transition: { staggerChildren: 0.018 } } }}
      >
        {words.map((w, i) => (
          <motion.span
            key={i}
            className="reveal-word"
            variants={{
              hidden: { opacity: 0, y: 10, filter: 'blur(6px)' },
              visible: { opacity: 1, y: 0, filter: 'blur(0px)' },
            }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          >
            {w}
            {' '}
          </motion.span>
        ))}
      </motion.span>
    </Tag>
  );
}

function HeroSection({ scrollRef, heroRef }) {
  const { scrollYProgress } = useScroll({
    target: heroRef,
    container: scrollRef,
    offset: ['start start', 'end start'],
  });
  const opacity = useTransform(scrollYProgress, [0, 0.8], [1, 0]);
  const y = useTransform(scrollYProgress, [0, 1], ['0%', '25%']);
  const scale = useTransform(scrollYProgress, [0, 1], [1, 1.08]);

  return (
    <section className="intro-hero" ref={heroRef}>
      <motion.div className="intro-hero-glow" style={{ scale }} />
      <motion.div className="intro-hero-content" style={{ opacity, y }}>
        <span className="intro-hero-eyebrow">TRỢ LÝ FIL</span>
        <RevealHeading as="h1" className="intro-hero-title">
          A Medical <br /> AI Assistant Project.
        </RevealHeading>
        <RevealBody as="p" className="intro-hero-subtitle">
          Full pipeline from diagnosis to treatment.
        </RevealBody>
      </motion.div>
      <motion.div className="intro-scroll-cue" style={{ opacity }}>
        <span>Cuộn để khám phá</span>
        <ChevronDown size={18} className="intro-scroll-cue-icon" />
      </motion.div>
    </section>
  );
}

function FeatureSection({ index, section, scrollRef, sectionRef }) {
  const Icon = section.icon;
  const Mock = section.mock;
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    container: scrollRef,
    offset: ['start end', 'end start'],
  });

  const textOpacity = useTransform(scrollYProgress, [0.15, 0.4, 0.75, 0.95], [0, 1, 1, 0]);
  const textY = useTransform(scrollYProgress, [0.15, 0.4], [40, 0]);
  const mockOpacity = useTransform(scrollYProgress, [0.2, 0.45, 0.8, 1], [0, 1, 1, 0.4]);
  const mockY = useTransform(scrollYProgress, [0.2, 0.5], [60, 0]);
  const mockScale = useTransform(scrollYProgress, [0.2, 0.5], [0.94, 1]);

  const reversed = index % 2 === 1;

  return (
    <section
      className={`intro-feature${reversed ? ' reversed' : ''}`}
      ref={sectionRef}
      data-section-index={index}
    >
      <motion.div className="intro-feature-text" style={{ opacity: textOpacity, y: textY }}>
        <div className="intro-feature-icon">
          <Icon size={20} />
        </div>
        <span className="intro-feature-eyebrow">{section.eyebrow}</span>
        <RevealHeading as="h2" className="intro-feature-title">
          {section.title}
        </RevealHeading>
        <RevealBody as="p" className="intro-feature-body">
          {section.body}
        </RevealBody>
      </motion.div>

      <motion.div
        className="intro-feature-mock"
        style={{ opacity: mockOpacity, y: mockY, scale: mockScale }}
      >
        <Mock />
      </motion.div>
    </section>
  );
}

// Animated loop layered above a .world-layer-image. Hides itself on error so a
// missing/broken file just reveals the static jpg underneath.
function BgVideo({ src, className = 'intro-bg-video', style }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    <video
      className={className}
      style={style}
      src={src}
      autoPlay
      muted
      loop
      playsInline
      preload="none"
      onError={() => setFailed(true)}
    />
  );
}

function ClosingSection({ onExit }) {
  return (
    <section className="intro-closing">
      <span className="intro-closing-eyebrow">SẴN SÀNG BẮT ĐẦU?</span>
      <RevealHeading as="h2" className="intro-closing-title">
        Bắt đầu với Trợ lý FII
      </RevealHeading>
      <button type="button" className="intro-closing-cta" onClick={onExit}>
        Vào trò chuyện <ArrowRight size={16} />
      </button>
      <RevealBody as="p" className="intro-closing-disclaimer">
        Thông tin chỉ mang tính chất tham khảo lâm sàng học thuật, quyết định điều trị cuối cùng thuộc về bác sĩ chuyên môn.
      </RevealBody>
    </section>
  );
}

// --- Feature mockups: stylized recreations of each tab's real UI, not screenshots ---

function ChatMock() {
  return (
    <>
      <div className="mock-window">
        <div className="mock-window-bar">
          <span /><span /><span />
        </div>
        <div className="mock-chat-body">
          <div className="mock-bubble user">Nam giới 55 tuổi, đau thượng vị kèm nôn ra máu, hướng xử trí?</div>
          <div className="mock-bubble ai">
            Ưu tiên nội soi cấp cứu trong 24h, đánh giá thang điểm Glasgow-Blatchford trước khi truyền dịch...
            <div className="mock-citation-chip"><FileText size={11} /> Nguồn: Xuất huyết tiêu hóa.pdf · tr. 42</div>
          </div>
          <div className="mock-bubble user">Thang điểm đó tính dựa trên yếu tố nào?</div>
          <div className="mock-bubble ai">
            Ure máu, Hb, huyết áp tâm thu, mạch, và biểu hiện lâm sàng đi kèm (ngất, suy tim, bệnh gan)...
            <div className="mock-citation-chip"><FileText size={11} /> Nguồn: Phác đồ nội soi cấp cứu.pdf · tr. 8</div>
          </div>
          <div className="mock-input-row">
            <span className="mock-input-placeholder">Nhập câu hỏi...</span>
            <span className="mock-mic-btn"><Mic size={13} /></span>
          </div>
        </div>
      </div>
      <div className="mock-highlight-badge"><CheckCircle2 size={13} /> Trích dẫn nguồn cho mọi câu trả lời</div>
    </>
  );
}

function MedicineMock() {
  return (
    <>
      <div className="mock-window">
        <div className="mock-window-bar"><span /><span /><span /></div>
        <div className="mock-medicine-body">
          <div className="mock-search-bar"><Search size={13} /> <span>omeprazole</span></div>
          <div className="mock-drug-card">
            <div className="mock-drug-card-head">
              <CheckCircle2 size={13} className="mock-drug-check" />
              <strong>Omeprazole</strong>
            </div>
            <p>Ức chế bơm proton, chỉ định trong loét dạ dày - tá tràng, GERD, dự phòng loét do NSAID...</p>
            <div className="mock-citation-chip"><FileText size={11} /> Dược thư quốc gia · tr. 118</div>
          </div>
          <div className="mock-drug-card">
            <div className="mock-drug-card-head">
              <CheckCircle2 size={13} className="mock-drug-check" />
              <strong>Liều dùng & thận trọng</strong>
            </div>
            <p>20-40mg/ngày, uống trước ăn sáng 30 phút; thận trọng dùng kéo dài trên bệnh nhân loãng xương...</p>
            <div className="mock-citation-chip"><FileText size={11} /> Dược thư quốc gia · tr. 119</div>
          </div>
        </div>
      </div>
      <div className="mock-highlight-badge"><CheckCircle2 size={13} /> Không qua AI tổng hợp — đúng từng câu chữ</div>
    </>
  );
}

function LibraryMock() {
  const files = [
    'Nội khoa cơ sở.pdf',
    'Dược lý học.pdf',
    'Xuất huyết tiêu hóa.pdf',
    'Chẩn đoán hình ảnh.pdf',
    'Phác đồ điều trị Bộ Y Tế.pdf',
    'Cấp cứu nội khoa.pdf',
  ];
  return (
    <>
      <div className="mock-window">
        <div className="mock-window-bar"><span /><span /><span /></div>
        <div className="mock-library-grid">
          {files.map((f) => (
            <div className="mock-file-card" key={f}>
              <FileText size={16} />
              <span>{f}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mock-highlight-badge"><CheckCircle2 size={13} /> Kho kiến thức đứng sau mọi câu trả lời</div>
    </>
  );
}

function PatientMock() {
  return (
    <>
      <div className="mock-window">
        <div className="mock-window-bar"><span /><span /><span /></div>
        <div className="mock-patient-body">
          <div className="mock-patient-head">
            <div className="mock-patient-avatar">NV</div>
            <div>
              <strong>Nguyễn Văn B</strong>
              <span>Nam · 62 tuổi · Tăng huyết áp, Đái tháo đường type 2</span>
            </div>
          </div>
          <div className="mock-visit-row"><span className="mock-visit-dot" />Khám 12/03 — Tăng huyết áp, chỉ định Amlodipine 5mg</div>
          <div className="mock-visit-row"><span className="mock-visit-dot" />Khám 02/06 — Tái khám định kỳ, huyết áp ổn định</div>
          <div className="mock-visit-row"><span className="mock-visit-dot" />Khám 20/08 — Xét nghiệm HbA1c định kỳ</div>
        </div>
      </div>
      <div className="mock-highlight-badge"><CheckCircle2 size={13} /> Sẵn sàng tra lại bất cứ lúc nào</div>
    </>
  );
}

function DiagnosisMock() {
  return (
    <>
      <div className="mock-window">
        <div className="mock-window-bar"><span /><span /><span /></div>
        <div className="mock-tree-body">
          <div className="mock-tree-node root">Đau thượng vị?</div>
          <div className="mock-tree-branches">
            <div className="mock-tree-node yes">Có → Nội soi</div>
            <div className="mock-tree-node no">Không → Theo dõi</div>
          </div>
          <div className="mock-tree-branches">
            <div className="mock-tree-node yes small">Loét (+) → Điều trị PPI</div>
            <div className="mock-tree-node no small">Loét (-) → Xét nguyên nhân khác</div>
          </div>
        </div>
      </div>
      <div className="mock-highlight-badge"><CheckCircle2 size={13} /> Từng bước một, có căn cứ rõ ràng</div>
    </>
  );
}
