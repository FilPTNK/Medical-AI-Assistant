import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import './DiagnosisWorkspace.css';
import AllergyCheckPanel from './AllergyCheckPanel';
import {
  Activity,
  AlertCircle,
  BookOpen,
  ClipboardList,
  Check,
  CheckCircle2,
  GitBranch,
  ListChecks,
  Info,
  Loader2,
  Maximize2,
  Sparkles,
  Stethoscope,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

/**
 * Tab "Chẩn đoán". Tách ra khỏi App.jsx ở commit trước; toàn bộ state vẫn nằm ở
 * App.jsx và đi vào đây bằng props.
 */
export default function DiagnosisTreeView({
  centerTreeCanvas,
  collectSymptoms,
  examLoading,
  examNotes,
  examResult,
  finalDiagnoses,
  finalLoading,
  handleFinalDiagnosis,
  handleGenerateTree,
  handleSuggestExam,
  handleToggleDiagnosisSelected,
  handleTreeCanvasMouseDown,
  handleSuggestTreatment,
  isPanningTree,
  isPreparingHandoff,
  nodeStatusMap,
  patientDesc,
  renderDecisionTreeNode,
  selectedDiagnosisDetail,
  selectedDiagnosisIds,
  treatmentResult,
  allergyCheck,
  setExamNotes,
  setPatientDesc,
  setSelectedDiagnosisDetail,
  treeCanvasRef,
  treeLoading,
  treePanOffset,
  treeRoot,
  treeWrapperRef,
  zoomScale,
  zoomTreeByDelta,
}) {
  const { confirmed, excluded } = treeRoot ? collectSymptoms(treeRoot, nodeStatusMap) : { confirmed: [], excluded: [] };
  const stage = finalLoading || finalDiagnoses.length ? 3 : examLoading || examResult ? 2 : treeRoot ? 1 : 0;
  const complete = finalDiagnoses.length > 0;
  const busy = treeLoading || examLoading || finalLoading;
  const stages = [
    ['Mô tả bệnh nhân', 'Thông tin đầu vào'],
    ['Triệu chứng', 'Xác nhận dấu hiệu'],
    ['Khám lâm sàng', 'Bổ sung kết quả'],
    ['Kết luận', 'Đối chiếu chẩn đoán'],
  ];
  return (
    <div className="fil-diagnosis-workspace">
      <ol className="dx-progress" aria-label="Tiến trình hỗ trợ chẩn đoán">
        {stages.map(([label, hint], index) => {
          const done = complete || index < stage;
          const current = index === stage && !complete;
          return <li key={label} className={done ? 'is-complete' : current ? 'is-current' : ''} aria-current={current ? 'step' : undefined}>
            <span className="dx-step-symbol" aria-hidden="true">{done ? <Check size={17} /> : current && busy ? <Loader2 size={17} className="animate-spin" /> : index + 1}</span>
            <div><span className="dx-step-label">{label}</span><span className="dx-step-hint">{current && busy ? 'Đang xử lý…' : hint}</span><span className="sr-only">{done ? 'Đã hoàn tất' : current ? 'Đang thực hiện' : 'Chưa thực hiện'}</span></div>
          </li>;
        })}
      </ol>
      <div className="diagnosis-split-layout">
          {/* Column 1: Questionnaire Area (70%) */}
          <div className="column-questionnaire animate-fade-in">
            <section className="patient-desc-section dx-description-card" aria-labelledby="diagnosis-description-label">
              <div className="patient-desc-header">
                <span className="dx-section-icon"><ClipboardList size={22} aria-hidden="true" /></span>
                <div><label id="diagnosis-description-label" htmlFor="diagnosis-patient-description">Nhập mô tả bệnh nhân</label><p id="diagnosis-description-hint">Ghi rõ triệu chứng, diễn tiến, tiền sử và thông tin liên quan.</p></div>
              </div>
              <textarea
                id="diagnosis-patient-description"
                className="patient-desc-textarea patient-desc-main"
                aria-describedby="diagnosis-description-hint"
                placeholder="Bắt đầu với lý do khám và mô tả tình trạng bệnh nhân…"
                value={patientDesc}
                onChange={(event) => setPatientDesc(event.target.value)}
              />
              <div className="patient-desc-actions">
                <span className="dx-input-note">Có thể cập nhật mô tả và tạo lại cây triệu chứng.</span>
                <button type="button" className="btn-analyze-desc" onClick={handleGenerateTree} disabled={treeLoading || !patientDesc.trim()}>
                  {treeLoading ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : <Sparkles size={18} aria-hidden="true" />}
                  <span>{treeLoading ? 'Đang tạo cây…' : 'Tạo cây chẩn đoán'}</span>
                </button>
              </div>
            </section>

            <section className="symptom-tree-card dx-tree-card" aria-labelledby="diagnosis-tree-title">
              <div className="symptom-tree-header">
                <h2 className="symptom-tree-title" id="diagnosis-tree-title"><span className="dx-section-icon"><GitBranch size={22} aria-hidden="true" /></span>Cây triệu chứng</h2>
                <span className="dx-tree-state">{treeLoading ? 'Đang phân tích' : treeRoot ? 'Sẵn sàng khai thác' : 'Chờ mô tả bệnh nhân'}</span>
              </div>
              <div className="symptom-tree-legend" aria-label="Chú thích trạng thái triệu chứng">
                <span className="legend-item"><span className="legend-dot yes" aria-hidden="true" />Đã chọn Có</span>
                <span className="legend-item"><span className="legend-x" aria-hidden="true">×</span>Đã chọn Không</span>
                <span className="legend-item"><span className="legend-dot unselected" aria-hidden="true" />Chưa chọn</span>
              </div>
              <div ref={treeWrapperRef} className={`tree-canvas-wrapper${!treeRoot ? ' is-empty' : ''}${isPanningTree ? ' panning' : ''}`} onMouseDown={treeRoot ? handleTreeCanvasMouseDown : undefined}>
                {treeLoading ? <div className="dx-canvas-empty" role="status"><span className="dx-loading-symbol"><Loader2 size={30} className="animate-spin" aria-hidden="true" /></span><h3>Đang xây dựng cây triệu chứng</h3><p>Hệ thống đang phân tích mô tả bệnh nhân.</p></div>
                  : !treeRoot ? <div className="dx-canvas-empty">
                    <svg className="dx-empty-branches" viewBox="0 0 240 130" fill="none" aria-hidden="true"><path d="M120 48v25M48 98V83a10 10 0 0 1 10-10h124a10 10 0 0 1 10 10v15M120 73v25" /><rect x="82" y="13" width="76" height="36" rx="12" /><rect x="18" y="98" width="60" height="25" rx="9" /><rect x="90" y="98" width="60" height="25" rx="9" /><rect x="162" y="98" width="60" height="25" rx="9" /><path d="M104 31h32M35 110h26M107 110h26M179 110h26" /></svg>
                    <h3>Bắt đầu từ mô tả bệnh nhân</h3><p>Nhập thông tin ở trên và chọn <strong>Tạo cây chẩn đoán</strong> để mở sơ đồ khai thác triệu chứng.</p>
                  </div> : <div ref={treeCanvasRef} className="symptom-tree-canvas" style={{ transform: `translate(${treePanOffset.x}px, ${treePanOffset.y}px) scale(${zoomScale})`, transformOrigin: '0 0' }}><div className="decision-tree-container">{renderDecisionTreeNode(treeRoot)}</div></div>}
                <div className="dx-canvas-toolbar">
                  <span className="dx-canvas-hint">{treeRoot ? 'Kéo để di chuyển · Ctrl + cuộn để thu phóng' : 'Sơ đồ khai thác triệu chứng'}</span>
                  <div className="zoom-controls" role="group" aria-label="Điều khiển sơ đồ">
                    <button type="button" className="zoom-btn" aria-label="Thu nhỏ sơ đồ" title="Thu nhỏ" disabled={!treeRoot || treeLoading} onClick={() => zoomTreeByDelta(-0.1)}><ZoomOut size={17} aria-hidden="true" /></button>
                    <button type="button" className="zoom-indicator" aria-label="Đặt lại thu phóng 100%" title="Đặt lại 100%" disabled={!treeRoot || treeLoading} onClick={() => centerTreeCanvas(1)}>{Math.round(zoomScale * 100)}%</button>
                    <button type="button" className="zoom-btn" aria-label="Phóng to sơ đồ" title="Phóng to" disabled={!treeRoot || treeLoading} onClick={() => zoomTreeByDelta(0.1)}><ZoomIn size={17} aria-hidden="true" /></button>
                    <button type="button" className="zoom-btn" aria-label="Căn vừa sơ đồ" title="Khít màn hình" disabled={!treeRoot || treeLoading} onClick={() => centerTreeCanvas(0.85)}><Maximize2 size={17} aria-hidden="true" /></button>
                  </div>
                </div>
              </div>
            </section>

            {/* Section 3: Gợi ý khám & nội soi */}
            <section className="symptom-tree-card dx-exam-card">
              <h2 className="symptom-tree-title"><span className="dx-section-icon"><Stethoscope size={22} aria-hidden="true" /></span>Gợi ý khám & nội soi</h2>
              <p className="dx-exam-hint">{!treeRoot ? 'Tạo cây triệu chứng để bắt đầu bước khám.' : !confirmed.length ? 'Chọn ít nhất một triệu chứng Có trên sơ đồ để nhận gợi ý khám.' : 'Các triệu chứng đã chọn sẽ được dùng để gợi ý khám.'}</p>
              <div className="diagnose-action-bar" style={{ border: 'none', padding: '0', background: 'transparent', marginTop: '0', boxShadow: 'none' }}>
                <button
                  type="button"
                  className="btn-diagnose-submit"
                  onClick={handleSuggestExam}
                  disabled={examLoading || !treeRoot || confirmed.length === 0}
                >
                  {examLoading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Stethoscope size={16} />
                  )}
                  <span>{examLoading ? 'Đang tổng hợp gợi ý…' : 'Gợi ý khám & nội soi'}</span>
                </button>
              </div>
            </section>

            {/* Section 4: Kết quả gợi ý khám & nội soi + nhập kết quả thực tế */}
            {examResult && (
              <div className="symptom-tree-card" style={{ marginTop: '0px' }}>
                <div className="symptom-tree-title">
                  <span className="dx-section-icon"><ListChecks size={22} aria-hidden="true" /></span>
                  <span>Kết quả gợi ý khám & nội soi</span>
                </div>

                <div className="endoscopy-focus-grid">
                  {(examResult.endoscopy_focus || []).map((item, idx) => (
                    <div key={idx} className="endoscopy-focus-card">
                      <h4>{item.region}</h4>
                      <p>{item.instructions}</p>
                    </div>
                  ))}
                </div>

                {(examResult.physical_exam_focus || []).length > 0 && (
                  <div style={{ marginTop: '14px' }}>
                    <h5 style={{ margin: '0 0 6px 0', fontSize: '13px', color: 'var(--text-secondary)' }}>Thao tác khám lâm sàng cần làm:</h5>
                    <ul className="markdown-bullet-list" style={{ margin: 0 }}>
                      {examResult.physical_exam_focus.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(examResult.key_signs_to_look_for || []).length > 0 && (
                  <div style={{ marginTop: '14px' }}>
                    <h5 style={{ margin: '0 0 6px 0', fontSize: '13px', color: 'var(--text-secondary)' }}>Dấu hiệu thực thể cần truy tìm:</h5>
                    <ul className="markdown-bullet-list" style={{ margin: 0 }}>
                      {examResult.key_signs_to_look_for.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: '18px' }}>
                  <label className="dx-findings-label" htmlFor="diagnosis-exam-findings">Kết quả khám lâm sàng & nội soi thực tế</label>
                  <textarea
                    id="diagnosis-exam-findings"
                    className="patient-desc-textarea"
                    style={{ minHeight: '110px' }}
                    placeholder="Ví dụ: Niêm mạc mũi xung huyết nhẹ, khe giữa bên phải có ít mủ đục chảy ra từ ngách bướm sàng. Vòm họng nhẵn bóng. Màng nhĩ 2 bên sáng, nón sáng rõ. Dây thanh khép kín, di động tốt."
                    value={examNotes}
                    onChange={(e) => setExamNotes(e.target.value)}
                  />
                </div>

                <div className="diagnose-action-bar" style={{ border: 'none', padding: '0', background: 'transparent', marginTop: '14px', boxShadow: 'none' }}>
                  <button
                    type="button"
                    className="btn-diagnose-submit"
                    onClick={handleFinalDiagnosis}
                    disabled={finalLoading || !examNotes.trim()}
                  >
                    {finalLoading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Activity size={16} />
                    )}
                    <span>{finalLoading ? 'Đang đối chiếu chẩn đoán…' : 'Tiến hành chẩn đoán cuối cùng'}</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Column 2: Results Area (30%) */}
          <aside className="column-results animate-fade-in" aria-label="Tổng hợp kết quả">
            {/* Selected symptoms card */}
            <section className="results-card dx-symptoms-card" aria-labelledby="dx-selected-title">
              <>
                    <h3 className="results-card-title" id="dx-selected-title">
                      <span><ListChecks size={19} aria-hidden="true" /> Triệu chứng đã chọn</span>
                      <span className="results-card-badge">
                        {confirmed.length}
                      </span>
                    </h3>
                    <div className="dx-symptom-totals"><span><CheckCircle2 size={14} aria-hidden="true" /> Có: {confirmed.length}</span><span><X size={14} aria-hidden="true" /> Loại trừ: {excluded.length}</span></div>
                    <div className="selected-symptoms-scroller">
                      {confirmed.length === 0 && excluded.length === 0 ? (
                        <p className="dx-rail-hint">Chọn các dấu hiệu trên sơ đồ. Những triệu chứng đã ghi nhận và loại trừ sẽ xuất hiện tại đây.</p>
                      ) : (
                        <div className="selected-symptoms-group">
                          {confirmed.map((label, idx) => (
                            <div key={`yes-${idx}`} className="selected-symptom-bullet" style={{ alignItems: 'flex-start', marginBottom: '8px' }}>
                              <span className="selected-symptom-dot" style={{ marginTop: '5px' }}></span>
                              <span style={{ fontWeight: '600' }}>{label}</span>
                            </div>
                          ))}
                          {excluded.map((label, idx) => (
                            <div key={`no-${idx}`} className="selected-symptom-bullet excluded" style={{ alignItems: 'flex-start', marginBottom: '8px' }}>
                              <span className="selected-symptom-dot" style={{ marginTop: '5px' }}></span>
                              <span style={{ textDecoration: 'line-through', color: 'var(--text-muted)' }}>{label}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
              </>
            </section>

            {/* Final Diagnosis List Card */}
            <section className="results-card dx-results-card" aria-labelledby="dx-results-title">
              <h3 className="results-card-title" id="dx-results-title">
                <span><ClipboardList size={19} aria-hidden="true" /> Kết quả chẩn đoán</span>
              </h3>

              <div style={{ flex: 1, overflowY: 'auto' }}>
                {finalDiagnoses.length === 0 ? (
                  <div className="dx-results-empty" role={finalLoading ? 'status' : undefined}>{finalLoading ? <Loader2 size={26} className="animate-spin" aria-hidden="true" /> : <ClipboardList size={28} strokeWidth={1.4} aria-hidden="true" />}<h4>{finalLoading ? 'Đang đối chiếu kết quả' : 'Chưa có kết quả chẩn đoán'}</h4><p>{finalLoading ? 'Hệ thống đang tổng hợp thông tin lâm sàng đã cung cấp.' : 'Hoàn tất khai thác triệu chứng và bổ sung kết quả khám để tiếp tục.'}</p></div>
                ) : (
                  <div className="causes-list">
                    {finalDiagnoses.map((diag, idx) => {
                      const pct = diag.confidence;
                      let statusClass = 'low-pct';
                      if (pct >= 70) statusClass = 'high-pct';
                      else if (pct >= 40) statusClass = 'medium-pct';

                      const isSelected = selectedDiagnosisIds.has(idx);
                      return (
                        <div
                          key={idx}
                          className={`cause-item ${statusClass} ${isSelected ? 'selected' : ''}`}
                          onClick={() => handleToggleDiagnosisSelected(idx)}
                        >
                          <div className="cause-item-top">
                            <span className="cause-item-name">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onClick={(e) => e.stopPropagation()}
                                onChange={() => handleToggleDiagnosisSelected(idx)}
                                aria-label={`Chọn chẩn đoán ${diag.disease_name}`}
                                style={{ marginRight: '6px', cursor: 'pointer' }}
                              />
                              {idx + 1}. {diag.disease_name}
                              {diag.icd10 && <span className="icd10-badge">{diag.icd10}</span>}
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <button
                                type="button"
                                className="icon-btn-action"
                                title="Xem chi tiết lý luận lâm sàng"
                                onClick={(e) => { e.stopPropagation(); setSelectedDiagnosisDetail(diag); }}
                              >
                                <Info size={13} />
                              </button>
                              <span className="cause-item-pct">{pct}%</span>
                            </span>
                          </div>
                          <div className="cause-item-bar-bg">
                            <div className="cause-item-bar-fill" style={{ width: `${pct}%` }}></div>
                          </div>
                          {diag.red_flags && (
                            <div className="red-flag-text">
                              <AlertCircle size={11} /> {diag.red_flags}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {finalDiagnoses.length > 0 && (
                <div style={{ marginTop: '16px', borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
                  <button
                    type="button"
                    className="btn-suggestion-chip"
                    style={{ width: '100%', display: 'flex', justifyContent: 'center', margin: 0 }}
                    onClick={() => {
                      if (finalDiagnoses.length === 0) return;
                      const firstSelectedIdx = [...selectedDiagnosisIds].sort((a, b) => a - b)[0];
                      setSelectedDiagnosisDetail(finalDiagnoses[firstSelectedIdx ?? 0]);
                    }}
                  >
                    <BookOpen size={13} style={{ marginRight: '6px' }} /> Xem chi tiết lý luận lâm sàng
                  </button>
                  <button
                    type="button"
                    className="btn-diagnose-submit"
                    style={{ width: '100%', marginTop: '10px' }}
                    onClick={handleSuggestTreatment}
                    disabled={selectedDiagnosisIds.size === 0 || isPreparingHandoff}
                  >
                    {isPreparingHandoff ? <Loader2 size={16} className="animate-spin" /> : <ClipboardList size={16} />} Gợi ý điều trị{selectedDiagnosisIds.size > 0 ? ` (${selectedDiagnosisIds.size} chẩn đoán)` : ''}
                  </button>

                  {treatmentResult && (
                    <section className="treatment-result" aria-label="Gợi ý điều trị">
                      <h3 className="treatment-result-title">Gợi ý điều trị</h3>
                      <p className="treatment-result-for">
                        Cho: {treatmentResult.diagnoses.map(d => d.disease_name).join(', ')}
                      </p>
                      <AllergyCheckPanel check={allergyCheck} />
                      {(treatmentResult.medications || []).length > 0 ? (
                        <ul className="treatment-med-list">
                          {treatmentResult.medications.map((m, i) => (
                            <li key={i} className="treatment-med">
                              <strong>{m.name}</strong>
                              <span className="treatment-med-dose">
                                {[m.dosage, m.form, m.frequency].filter(Boolean).join(' · ')}
                              </span>
                              {m.instructions && <span className="treatment-med-note">{m.instructions}</span>}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="treatment-empty">
                          Tài liệu trong kho không đủ căn cứ để gợi ý thuốc cụ thể cho chẩn đoán này.
                        </p>
                      )}
                      {[
                        ['Không dùng thuốc', treatmentResult.no_drug_recommendations],
                        ['Chăm sóc tại nhà', treatmentResult.care_instructions],
                        ['Lưu ý', treatmentResult.precautions],
                      ].filter(([, v]) => v && String(v).trim()).map(([label, v]) => (
                        <div key={label} className="treatment-block">
                          <h4>{label}</h4>
                          <p>{v}</p>
                        </div>
                      ))}
                    </section>
                  )}
                </div>
              )}
            </section>
          </aside>
      </div>

          {/* Diagnosis Details Modal popup */}
          {selectedDiagnosisDetail && (
            <Dialog.Root open onOpenChange={open => { if (!open) setSelectedDiagnosisDetail(null); }}><Dialog.Portal><Dialog.Overlay className="dx-detail-overlay" />
              <Dialog.Content className="diagnosis-modal dx-detail-dialog" aria-describedby={undefined}>
                <div className="diagnosis-modal-header">
                  <Dialog.Title asChild><h3>Chi tiết bệnh lý gợi ý</h3></Dialog.Title>
                  <button className="icon-btn-action" aria-label="Đóng chi tiết chẩn đoán" onClick={() => setSelectedDiagnosisDetail(null)}><X size={16} /></button>
                </div>
                <div className="diagnosis-modal-body">
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', gap: '10px' }}>
                      <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 'bold', color: 'var(--text-primary)' }}>{selectedDiagnosisDetail.disease_name}</h4>
                      <span className="badge-beta" style={{ background: 'var(--bg-app)', color: 'var(--primary)', flexShrink: 0 }}>{selectedDiagnosisDetail.confidence}% phù hợp</span>
                    </div>
                    {selectedDiagnosisDetail.icd10 && (
                      <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '0 0 16px 0' }}>
                        <strong>Mã ICD-10:</strong> {selectedDiagnosisDetail.icd10}
                      </p>
                    )}
                  </div>

                  {selectedDiagnosisDetail.red_flags && (
                    <div style={{ background: 'rgba(239, 68, 68, 0.08)', padding: '12px 16px', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.3)', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                      <AlertCircle size={16} style={{ color: '#ef4444', flexShrink: 0, marginTop: '2px' }} />
                      <p style={{ fontSize: '13px', lineHeight: '1.6', margin: 0, color: '#ef4444' }}>
                        {selectedDiagnosisDetail.red_flags}
                      </p>
                    </div>
                  )}

                  <div style={{ background: 'var(--bg-app)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                    <h5 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 'bold', color: 'var(--text-secondary)' }}>Lý luận lâm sàng của AI:</h5>
                    <p style={{ fontSize: '13px', lineHeight: '1.6', margin: 0, color: 'var(--text-primary)' }}>
                      {selectedDiagnosisDetail.reasoning}
                    </p>
                  </div>
                </div>
                <div className="diagnosis-modal-footer">
                  <button className="btn-secondary" onClick={() => setSelectedDiagnosisDetail(null)}>Đóng</button>
                </div>
              </Dialog.Content>
            </Dialog.Portal></Dialog.Root>
          )}
        </div>
  );
}
