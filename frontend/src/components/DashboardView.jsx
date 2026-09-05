import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, Users, UserPlus, RefreshCw, Loader2, AlertCircle, Table2,
  BarChart3, Stethoscope, Pill, CalendarClock, TrendingUp, TrendingDown,
} from 'lucide-react';
import { apiJson } from '../lib/apiClient';
import './DashboardView.css';

/**
 * Thống kê phòng khám: số ca theo bệnh, thuốc kê nhiều nhất, xu hướng theo thời gian.
 *
 * Biểu đồ vẽ tay bằng SVG/CSS thay vì kéo thêm thư viện: dữ liệu ở đây là các
 * dạng đơn giản (một đường theo thời gian, các thanh xếp hạng) nên chi phí một
 * thư viện chart không đáng so với ~200 dòng.
 *
 * Quy ước màu (đã kiểm định độ tương phản và mù màu trên đúng nền của ứng dụng):
 * chuỗi 1 xanh dương, chuỗi 2 cam. Bảng xếp hạng chỉ có một chuỗi nên dùng đúng
 * một màu cho mọi thanh — độ dài thanh đã mã hóa giá trị, không tô đậm nhạt theo
 * giá trị nữa.
 */

const RANGES = [
  { id: '7', label: '7 ngày', days: 7 },
  { id: '30', label: '30 ngày', days: 30 },
  { id: '90', label: '90 ngày', days: 90 },
  { id: '365', label: '12 tháng', days: 365 },
];

const isoDaysAgo = (days) => {
  const d = new Date();
  d.setDate(d.getDate() - days + 1);
  return d.toISOString().slice(0, 10);
};

const todayIso = () => new Date().toISOString().slice(0, 10);

/** 1.284 → "1.284"; 12900 → "12,9K". Số lớn trên thẻ chỉ số phải liếc là đọc được. */
const compact = (n) => {
  const value = Number(n) || 0;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (Math.abs(value) >= 10_000) return `${(value / 1000).toFixed(1).replace('.', ',')}K`;
  return value.toLocaleString('vi-VN');
};

const pct = (n) => `${(Number(n) || 0).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;

// --- Khối dựng biểu đồ ----------------------------------------------------

function StatTile({ icon: Icon, label, value, unit, delta, deltaLabel, tone = 'neutral' }) {
  const hasDelta = delta !== null && delta !== undefined && Number.isFinite(delta);
  const direction = hasDelta ? (delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat') : null;
  return (
    <div className={`dv-tile dv-tile-${tone}`}>
      <div className="dv-tile-head">
        <span className="dv-tile-label">{label}</span>
        {Icon && <Icon size={15} className="dv-tile-icon" />}
      </div>
      <div className="dv-tile-value">
        {value}
        {unit && <span className="dv-tile-unit">{unit}</span>}
      </div>
      {hasDelta ? (
        <div className={`dv-tile-delta dv-delta-${direction}`}>
          {direction === 'up' ? <TrendingUp size={13} /> : direction === 'down' ? <TrendingDown size={13} /> : null}
          <span>{delta > 0 ? '+' : ''}{pct(delta)}</span>
          <span className="dv-tile-delta-note">{deltaLabel}</span>
        </div>
      ) : (
        deltaLabel && <div className="dv-tile-delta dv-delta-flat"><span className="dv-tile-delta-note">{deltaLabel}</span></div>
      )}
    </div>
  );
}

/**
 * Biểu đồ đường hai chuỗi có thước ngắm và chú giải theo con trỏ.
 * Trục y duy nhất cho cả hai chuỗi — không bao giờ dùng hai thang đo trên một khung.
 */
function TrendChart({ series, points, granularity }) {
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);

  const W = 760, H = 250;
  const pad = { top: 16, right: 18, bottom: 30, left: 42 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const maxValue = Math.max(1, ...points.flatMap((p) => series.map((s) => p[s.key] || 0)));
  // Làm tròn trần lên số đẹp để vạch trục là 0 / 5 / 10 chứ không phải 0 / 3,7 / 7,4.
  const step = Math.max(1, Math.ceil(maxValue / 4));
  const niceStep = step <= 2 ? step : step <= 5 ? 5 : Math.ceil(step / 10) * 10;
  const yMax = niceStep * 4;

  const x = (i) => pad.left + (points.length <= 1 ? plotW / 2 : (i * plotW) / (points.length - 1));
  const y = (v) => pad.top + plotH - ((v || 0) / yMax) * plotH;

  const pathOf = (key) => points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(p[key])}`).join(' ');
  const areaOf = (key) => `${pathOf(key)} L${x(points.length - 1)},${pad.top + plotH} L${x(0)},${pad.top + plotH} Z`;

  const ticks = [0, 1, 2, 3, 4].map((i) => i * niceStep);

  // Nhãn trục x thưa dần theo số điểm để chữ không chồng nhau.
  const labelEvery = Math.max(1, Math.ceil(points.length / 8));

  const handleMove = (event) => {
    const svg = svgRef.current;
    if (!svg || points.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const svgX = ratio * W;
    const index = Math.round(((svgX - pad.left) / plotW) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, index)));
  };

  if (!points.length) {
    return <div className="dv-empty">Chưa có dữ liệu trong khoảng thời gian này.</div>;
  }

  const active = hover !== null ? points[hover] : null;

  return (
    <div className="dv-chart-wrap">
      <div className="dv-legend">
        {series.map((s) => (
          <span className="dv-legend-item" key={s.key}>
            <span className="dv-legend-key" style={{ background: `var(${s.color})` }} />
            {s.label}
          </span>
        ))}
      </div>

      <div className="dv-svg-scroll">
        <svg
          ref={svgRef}
          className="dv-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Xu hướng ${series.map((s) => s.label).join(' và ')} theo thời gian`}
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={W - pad.right} y1={y(t)} y2={y(t)} className="dv-grid" />
              <text x={pad.left - 8} y={y(t) + 4} className="dv-axis-text" textAnchor="end">{t}</text>
            </g>
          ))}

          {points.map((p, i) => (
            i % labelEvery === 0 ? (
              <text key={p.key} x={x(i)} y={H - 10} className="dv-axis-text" textAnchor="middle">{p.label}</text>
            ) : null
          ))}

          {series.map((s) => (
            <path key={`a-${s.key}`} d={areaOf(s.key)} fill={`var(${s.color})`} opacity="0.1" />
          ))}
          {series.map((s) => (
            <path
              key={`l-${s.key}`}
              d={pathOf(s.key)}
              fill="none"
              stroke={`var(${s.color})`}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}

          {hover !== null && (
            <>
              <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + plotH} className="dv-crosshair" />
              {series.map((s) => (
                <circle
                  key={`d-${s.key}`}
                  cx={x(hover)}
                  cy={y(points[hover][s.key])}
                  r="4.5"
                  fill={`var(${s.color})`}
                  className="dv-dot"
                />
              ))}
            </>
          )}
        </svg>

        {active && (
          <div
            className="dv-tooltip"
            style={{ left: `${((x(hover) - pad.left) / plotW) * 100}%` }}
          >
            <strong>{active.label}</strong>
            {series.map((s) => (
              <span key={s.key}>
                <i style={{ background: `var(${s.color})` }} />
                {s.label}: <b>{active[s.key] || 0}</b>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="dv-chart-note">
        Mốc thời gian: {granularity === 'month' ? 'theo tháng' : granularity === 'week' ? 'theo tuần' : 'theo ngày'}
      </div>
    </div>
  );
}

/** Bảng xếp hạng dạng thanh ngang — một chuỗi, một màu, giá trị ghi ở đầu thanh. */
function RankBars({ rows, emptyText, unitLabel = 'ca', showPatients = false }) {
  if (!rows?.length) return <div className="dv-empty">{emptyText}</div>;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <ul className="dv-rank">
      {rows.map((row) => (
        <li className="dv-rank-row" key={row.label}>
          <div className="dv-rank-head">
            <span className="dv-rank-label" title={row.label}>{row.label}</span>
            <span className="dv-rank-value">
              {row.count.toLocaleString('vi-VN')} {unitLabel}
              <small>{pct(row.percent)}</small>
            </span>
          </div>
          <div className="dv-rank-track">
            <div className="dv-rank-fill" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
          {showPatients && row.patients != null && (
            <span className="dv-rank-sub">{row.patients} bệnh nhân</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Biểu đồ cột gọn cho nhóm tuổi / ngày trong tuần. */
function MiniColumns({ rows, emptyText }) {
  if (!rows?.length || rows.every((r) => !r.count)) {
    return <div className="dv-empty">{emptyText}</div>;
  }
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div className="dv-columns">
      {rows.map((row) => (
        <div className="dv-column" key={row.label} title={`${row.label}: ${row.count}`}>
          <span className="dv-column-value">{row.count || ''}</span>
          <div className="dv-column-track">
            {/* Mốc bằng 0 không vẽ cột: một vạch 2px ở chân trục trông như nhiễu
                chứ không đọc ra là "không có ca nào". */}
            <div
              className="dv-column-fill"
              style={{ height: row.count ? `${Math.max(2, (row.count / max) * 100)}%` : 0 }}
            />
          </div>
          <span className="dv-column-label">{row.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Tỷ lệ theo hạng mục định danh (giới tính, nhóm máu) — thanh xếp chồng + chú giải. */
function SplitBar({ rows, emptyText }) {
  const total = (rows || []).reduce((sum, r) => sum + r.count, 0);
  if (!total) return <div className="dv-empty">{emptyText}</div>;
  const slots = ['--dv-series-1', '--dv-series-2', '--dv-series-3'];
  const shown = rows.slice(0, 3);
  const rest = rows.slice(3).reduce((sum, r) => sum + r.count, 0);
  const items = rest ? [...shown, { label: 'Khác', count: rest }] : shown;

  return (
    <div className="dv-split">
      <div className="dv-split-bar">
        {items.map((row, i) => (
          <div
            key={row.label}
            className="dv-split-seg"
            style={{
              width: `${(row.count / total) * 100}%`,
              background: i < slots.length ? `var(${slots[i]})` : 'var(--text-muted)',
            }}
            title={`${row.label}: ${row.count}`}
          />
        ))}
      </div>
      <ul className="dv-split-legend">
        {items.map((row, i) => (
          <li key={row.label}>
            <span
              className="dv-legend-key"
              style={{ background: i < slots.length ? `var(${slots[i]})` : 'var(--text-muted)' }}
            />
            <span className="dv-split-name">{row.label}</span>
            <b>{row.count}</b>
            <small>{pct((row.count / total) * 100)}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Bảng số liệu — kênh truy cập thay thế cho mọi biểu đồ trên trang. */
function DataTable({ columns, rows }) {
  if (!rows?.length) return <div className="dv-empty">Không có số liệu.</div>;
  return (
    <div className="dv-table-scroll">
      <table className="dv-table">
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Card({ title, subtitle, icon: Icon, children, action }) {
  return (
    <section className="dv-card">
      <header className="dv-card-head">
        <div>
          <h3>{Icon && <Icon size={15} />} {title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

// --- Trang thống kê -------------------------------------------------------

export default function DashboardView({ permissions, onOpenPatient }) {
  const [rangeId, setRangeId] = useState('90');
  const [scope, setScope] = useState(permissions.seesAllPatients ? 'clinic' : 'mine');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tableView, setTableView] = useState(false);

  const range = useMemo(() => RANGES.find((r) => r.id === rangeId) || RANGES[2], [rangeId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams({
      date_from: isoDaysAgo(range.days),
      date_to: todayIso(),
    });
    if (scope === 'mine') params.set('scope', 'mine');
    const qs = params.toString();

    try {
      const [overview, diagnoses, medications, trends, demographics] = await Promise.all([
        apiJson(`/api/stats/overview?${qs}`),
        apiJson(`/api/stats/diagnoses?${qs}`),
        apiJson(`/api/stats/medications?${qs}`),
        apiJson(`/api/stats/trends?${qs}`),
        apiJson(`/api/stats/demographics?${scope === 'mine' ? 'scope=mine' : ''}`),
      ]);
      // Bảng theo bác sĩ chỉ dành cho quản trị; lỗi ở đây không nên làm hỏng cả trang.
      let doctors = null;
      if (permissions.isAdmin) {
        try {
          doctors = await apiJson(`/api/stats/doctors?${qs}`);
        } catch { /* bỏ qua, phần còn lại vẫn hiển thị */ }
      }
      setData({ overview, diagnoses, medications, trends, demographics, doctors });
    } catch (err) {
      setError(err.message || 'Không tải được số liệu thống kê.');
    } finally {
      setLoading(false);
    }
  }, [range.days, scope, permissions.isAdmin]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return (
      <div className="dv-view">
        <div className="dv-state"><Loader2 size={22} className="dv-spin" /> Đang tổng hợp số liệu…</div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="dv-view">
        <div className="dv-state dv-state-error">
          <AlertCircle size={22} /> {error}
          <button type="button" className="dv-btn" onClick={load}><RefreshCw size={14} /> Thử lại</button>
        </div>
      </div>
    );
  }

  const { overview, diagnoses, medications, trends, demographics, doctors } = data;
  const reminders = overview.reminders || {};

  const trendSeries = [
    { key: 'visits', label: 'Lượt khám', color: '--dv-series-1' },
    { key: 'new_patients', label: 'Bệnh nhân mới', color: '--dv-series-2' },
  ];

  return (
    <div className="dv-view animate-fade-in">
      <div className="dv-topbar">
        <div>
          <h1 className="dv-title">Thống kê phòng khám</h1>
          <p className="dv-subtitle">
            {scope === 'mine' ? 'Bệnh nhân bạn phụ trách' : 'Toàn phòng khám'} ·
            {' '}{range.label.toLowerCase()} gần nhất
          </p>
        </div>

        <div className="dv-filters">
          {permissions.seesAllPatients && (
            <div className="dv-segmented" role="group" aria-label="Phạm vi thống kê">
              <button
                type="button"
                className={scope === 'clinic' ? 'active' : ''}
                onClick={() => setScope('clinic')}
              >Phòng khám</button>
              <button
                type="button"
                className={scope === 'mine' ? 'active' : ''}
                onClick={() => setScope('mine')}
              >Của tôi</button>
            </div>
          )}

          <div className="dv-segmented" role="group" aria-label="Khoảng thời gian">
            {RANGES.map((r) => (
              <button
                key={r.id}
                type="button"
                className={rangeId === r.id ? 'active' : ''}
                onClick={() => setRangeId(r.id)}
              >{r.label}</button>
            ))}
          </div>

          <button
            type="button"
            className={`dv-btn dv-btn-ghost ${tableView ? 'active' : ''}`}
            onClick={() => setTableView((v) => !v)}
            title="Xem số liệu dạng bảng"
          >
            {tableView ? <BarChart3 size={15} /> : <Table2 size={15} />}
            {tableView ? 'Biểu đồ' : 'Bảng'}
          </button>

          <button type="button" className="dv-btn dv-btn-ghost" onClick={load} title="Tải lại số liệu">
            <RefreshCw size={15} className={loading ? 'dv-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="dv-tiles">
        <StatTile
          icon={Activity} label="Lượt khám" value={compact(overview.visits)}
          delta={overview.visits_delta_pct} deltaLabel="so với kỳ trước"
        />
        <StatTile
          icon={UserPlus} label="Bệnh nhân mới" value={compact(overview.new_patients)}
          delta={overview.new_patients_delta_pct} deltaLabel="so với kỳ trước"
        />
        <StatTile
          icon={Users} label="Tổng bệnh nhân" value={compact(overview.total_patients)}
          deltaLabel={`${overview.active_patients} người có khám trong kỳ`}
        />
        <StatTile
          icon={RefreshCw} label="Tỷ lệ tái khám" value={pct(overview.return_rate_pct)}
          deltaLabel={`${overview.visits_per_patient} lượt/bệnh nhân`}
        />
        <StatTile
          icon={CalendarClock} label="Hẹn quá hạn" value={compact(reminders.overdue || 0)}
          tone={reminders.overdue ? 'warning' : 'neutral'}
          deltaLabel={`${reminders.pending_total || 0} lịch đang chờ`}
        />
      </div>

      <Card
        title="Xu hướng theo thời gian"
        subtitle="Lượt khám và bệnh nhân mới trong kỳ"
        icon={TrendingUp}
      >
        {tableView ? (
          <DataTable
            columns={['Mốc thời gian', 'Lượt khám', 'Bệnh nhân khám', 'Bệnh nhân mới']}
            rows={trends.series.map((s) => [s.label, s.visits, s.patients, s.new_patients])}
          />
        ) : (
          <TrendChart series={trendSeries} points={trends.series} granularity={trends.granularity} />
        )}
      </Card>

      <div className="dv-grid-2">
        <Card
          title="Số ca theo bệnh"
          subtitle={`${diagnoses.distinct_diagnoses} chẩn đoán khác nhau trên ${diagnoses.visits_with_diagnosis} lượt khám`}
          icon={Stethoscope}
        >
          {tableView ? (
            <DataTable
              columns={['Chẩn đoán', 'Số ca', 'Tỷ lệ', 'Bệnh nhân']}
              rows={diagnoses.primary.map((d) => [d.label, d.count, pct(d.percent), d.patients ?? '—'])}
            />
          ) : (
            <RankBars
              rows={diagnoses.primary}
              emptyText="Chưa có lượt khám nào ghi chẩn đoán trong kỳ."
              showPatients
            />
          )}
        </Card>

        <Card
          title="Thuốc kê nhiều nhất"
          subtitle={`${medications.prescriptions} đơn thuốc · trung bình ${medications.lines_per_prescription} thuốc/đơn`}
          icon={Pill}
        >
          {tableView ? (
            <DataTable
              columns={['Thuốc', 'Số lần kê', 'Tỷ lệ', 'Bệnh nhân']}
              rows={medications.medications.map((m) => [m.label, m.count, pct(m.percent), m.patients ?? '—'])}
            />
          ) : (
            <RankBars
              rows={medications.medications}
              emptyText="Chưa có đơn thuốc nào trong kỳ."
              unitLabel="lần"
              showPatients
            />
          )}
        </Card>
      </div>

      <div className="dv-grid-2">
        <Card title="Nhóm tuổi bệnh nhân" subtitle={`Tuổi trung bình ${demographics.average_age ?? '—'}`}>
          {tableView ? (
            <DataTable
              columns={['Nhóm tuổi', 'Số bệnh nhân']}
              rows={demographics.age_groups.map((g) => [g.label, g.count])}
            />
          ) : (
            <MiniColumns rows={demographics.age_groups} emptyText="Chưa đủ dữ liệu ngày sinh." />
          )}
        </Card>

        <Card title="Lượt khám theo ngày trong tuần" subtitle="Dùng để cân đối lịch trực">
          {tableView ? (
            <DataTable
              columns={['Ngày', 'Lượt khám']}
              rows={trends.by_weekday.map((d) => [d.label, d.count])}
            />
          ) : (
            <MiniColumns rows={trends.by_weekday} emptyText="Chưa có lượt khám nào trong kỳ." />
          )}
        </Card>
      </div>

      <div className="dv-grid-2">
        <Card title="Giới tính" subtitle={`${demographics.total} hồ sơ`}>
          <SplitBar rows={demographics.gender} emptyText="Chưa có hồ sơ nào." />
        </Card>

        <Card title="Bệnh mãn tính đang quản lý" subtitle="Tổng hợp từ tiền sử trong hồ sơ">
          {diagnoses.chronic?.length ? (
            <RankBars rows={diagnoses.chronic.slice(0, 8)} emptyText="" unitLabel="bệnh nhân" />
          ) : (
            <div className="dv-empty">Chưa hồ sơ nào khai bệnh mãn tính.</div>
          )}
        </Card>
      </div>

      {permissions.isAdmin && doctors?.doctors?.length > 0 && (
        <Card title="Khối lượng công việc theo bác sĩ" subtitle="Chỉ quản trị phòng khám xem được" icon={Users}>
          <DataTable
            columns={['Bác sĩ', 'Vai trò', 'Bệnh nhân phụ trách', 'Lượt khám trong kỳ', 'Hẹn quá hạn']}
            rows={doctors.doctors.map((d) => [
              d.doctor_name, d.role_label, d.patients, d.visits, d.overdue_followups,
            ])}
          />
        </Card>
      )}
    </div>
  );
}
