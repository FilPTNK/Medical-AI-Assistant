import React from 'react';
import AllergyCheckPanel from './AllergyCheckPanel';
import {
  Activity,
  AlertCircle,
  BookOpen,
  ClipboardList,
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
  return (
        <div className="diagnosis-split-layout">
          {/* Column 1: Questionnaire Area (70%) */}
          <div className="column-questionnaire animate-fade-in">
            {/* Section 1: Nhập mô tả bệnh nhân */}
            <div className="patient-desc-section">
              <div className="patient-desc-header">
                <span className="patient-desc-header-badge">1</span>
                <label htmlFor="diagnosis-patient-description">Nhập mô tả bệnh nhân</label>
              </div>
              <textarea
                id="diagnosis-patient-description"
                className="patient-desc-textarea patient-desc-main"
                placeholder="Nhập triệu chứng, tiền sử, thuốc đang dùng và dị ứng nếu có…"
                value={patientDesc}
                onChange={(e) => setPatientDesc(e.target.value)}
              />
              <div className="patient-desc-actions">
                <button
                  type="button"
                  className="btn-analyze-desc"
                  onClick={handleGenerateTree}
                  disabled={treeLoading || !patientDesc.trim()}
                >
                  {treeLoading ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Sparkles size={18} />
                  )}
                  <span>Tạo cây chẩn đoán</span>
                </button>
              </div>
            </div>

            {/* Section 2: Cây triệu chứng */}
            <div className="symptom-tree-card">
              <div className="symptom-tree-header">
                <div className="symptom-tree-title">
                  <span className="patient-desc-header-badge">2</span>
                  <span>Cây triệu chứng</span>
                </div>

                <div className="symptom-tree-header-right">
                  {/* Legend */}
                  <div className="symptom-tree-legend">
                    <div className="legend-item">
                      <span className="legend-dot yes"></span>
                      <span>Đã chọn 'Có'</span>
                    </div>
                    <div className="legend-item">
                      <span className="legend-dot unselected"></span>
                      <span>Chưa chọn</span>
                    </div>
                    <div className="legend-item">
                      <span className="legend-x">X</span>
                      <span>Đã chọn 'Không'</span>
                    </div>
                  </div>

                  {/* Zoom Controls */}
                  <div className="zoom-controls">
                    <button
                      type="button"
                      className="zoom-btn"
                      title="Thu nhỏ"
                      onClick={() => zoomTreeByDelta(-0.1)}
                    >
                      <ZoomOut size={14} />
                    </button>
                    <span
                      className="zoom-indicator"
                      style={{ cursor: 'pointer' }}
                      title="Đặt lại 100%"
                      onClick={() => centerTreeCanvas(1)}
                    >
                      {Math.round(zoomScale * 100)}%
                    </span>
                    <button
                      type="button"
                      className="zoom-btn"
                      title="Phóng to"
                      onClick={() => zoomTreeByDelta(0.1)}
                    >
                      <ZoomIn size={14} />
                    </button>
                    <button
                      type="button"
                      className="zoom-btn"
                      title="Khít màn hình"
                      onClick={() => centerTreeCanvas(0.85)}
                    >
                      <Maximize2 size={14} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Tree Canvas — infinite pan/zoom surface (drag to pan, scroll to zoom) */}
              <div
                ref={treeWrapperRef}
                className={`tree-canvas-wrapper${isPanningTree ? ' panning' : ''}`}
                onMouseDown={handleTreeCanvasMouseDown}
              >
                {treeLoading ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', height: '100%', color: 'var(--text-secondary)', fontSize: '13px' }}>
                    <Loader2 size={26} className="animate-spin" />
                    <span>Đang dựng cây chẩn đoán…</span>
                  </div>
                ) : !treeRoot ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)', fontSize: '13px', textAlign: 'center', padding: '0 20px' }}>
                    Chưa có cây chẩn đoán.
                  </div>
                ) : (
                  <div
                    ref={treeCanvasRef}
                    className="symptom-tree-canvas"
                    style={{
                      transform: `translate(${treePanOffset.x}px, ${treePanOffset.y}px) scale(${zoomScale})`,
                      transformOrigin: '0 0'
                    }}
                  >
                    <div className="decision-tree-container">
                      {renderDecisionTreeNode(treeRoot)}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Section 3: Gợi ý khám & nội soi */}
            <div className="symptom-tree-card" style={{ marginTop: '0px' }}>
              <div className="symptom-tree-title">
                <span className="patient-desc-header-badge">3</span>
                <span>Gợi ý khám & nội soi</span>
              </div>
              <div className="diagnose-action-bar" style={{ border: 'none', padding: '0', background: 'transparent', marginTop: '0', boxShadow: 'none' }}>
                <button
                  type="button"
                  className="btn-diagnose-submit"
                  onClick={handleSuggestExam}
                  disabled={examLoading || !treeRoot || collectSymptoms(treeRoot, nodeStatusMap).confirmed.length === 0}
                >
                  {examLoading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Stethoscope size={16} />
                  )}
                  <span>Gợi ý khám & nội soi</span>
                </button>
              </div>
            </div>

            {/* Section 4: Kết quả gợi ý khám & nội soi + nhập kết quả thực tế */}
            {examResult && (
              <div className="symptom-tree-card" style={{ marginTop: '0px' }}>
                <div className="symptom-tree-title">
                  <span className="patient-desc-header-badge">4</span>
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
                  <h5 style={{ margin: '0 0 6px 0', fontSize: '13px', color: 'var(--text-secondary)' }}>Nhập/Dán mô tả kết quả khám lâm sàng & nội soi Tai Mũi Họng:</h5>
                  <textarea
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
                    <span>Tiến hành chẩn đoán cuối cùng</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Column 2: Results Area (30%) */}
          <div className="column-results animate-fade-in">
            {/* Selected symptoms card */}
            <div className="results-card">
              {(() => {
                const { confirmed, excluded } = treeRoot ? collectSymptoms(treeRoot, nodeStatusMap) : { confirmed: [], excluded: [] };
                return (
                  <>
                    <h3 className="results-card-title">
                      <span>Triệu chứng đã chọn</span>
                      <span className="results-card-badge">
                        {confirmed.length}
                      </span>
                    </h3>
                    <div className="selected-symptoms-scroller">
                      {confirmed.length === 0 && excluded.length === 0 ? (
                        <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          Chưa chọn triệu chứng nào.
                        </div>
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
                );
              })()}
            </div>

            {/* Final Diagnosis List Card */}
            <div className="results-card" style={{ flex: 1 }}>
              <h3 className="results-card-title">
                <span>Kết quả chẩn đoán</span>
              </h3>

              <div style={{ flex: 1, overflowY: 'auto' }}>
                {finalDiagnoses.length === 0 ? (
                  <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', fontSize: '13px', textAlign: 'center', padding: '20px' }}>
                    Chưa có kết quả.
                  </div>
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
            </div>
          </div>

          {/* Diagnosis Details Modal popup */}
          {selectedDiagnosisDetail && (
            <div className="diagnosis-modal-overlay animate-fade-in" onClick={() => setSelectedDiagnosisDetail(null)}>
              <div className="diagnosis-modal" onClick={(e) => e.stopPropagation()}>
                <div className="diagnosis-modal-header">
                  <h3>Chi tiết bệnh lý gợi ý</h3>
                  <button className="icon-btn-action" aria-label="Đóng chi tiết chẩn đoán" onClick={() => setSelectedDiagnosisDetail(null)}><X size={16} /></button>
                </div>
                <div className="diagnosis-modal-body">
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', gap: '10px' }}>
                      <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 'bold', color: 'var(--text-primary)' }}>{selectedDiagnosisDetail.disease_name}</h4>
                      <span className="badge-beta" style={{ background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e', flexShrink: 0 }}>{selectedDiagnosisDetail.confidence}% phù hợp</span>
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
              </div>
            </div>
          )}
        </div>
  );
}
