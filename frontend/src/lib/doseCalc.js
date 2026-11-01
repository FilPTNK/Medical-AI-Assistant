/**
 * Tính liều theo cân nặng — thuần, tất định, không gọi mạng.
 *
 * Đầu vào đều do bác sĩ quyết (có thể điền sẵn từ một câu Dược thư, nhưng bác
 * sĩ thấy và sửa được từng ô). Hàm này chỉ làm phép nhân/chia và so với mức
 * trần, rồi NÓI RA khi vượt trần chứ không tự cắt: liều bị cắt im lặng là liều
 * khác với liều bác sĩ nghĩ mình đang kê.
 */

/** Làm tròn hiển thị: dưới 10 mg giữ 1 chữ số thập phân, từ 10 mg trở lên lấy số nguyên. */
export function roundMg(mg) {
  if (!Number.isFinite(mg)) return null;
  return mg < 10 ? Math.round(mg * 10) / 10 : Math.round(mg);
}

/** mL làm tròn 0,1 — vạch chia của bơm/cốc đo uống nhỏ nhất thường gặp. */
export function roundMl(ml) {
  return Number.isFinite(ml) ? Math.round(ml * 10) / 10 : null;
}

const num = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : null;
};

/**
 * @param {object} p
 * @param {number} p.weightKg       cân nặng
 * @param {number} p.mgPerKg        liều mg/kg
 * @param {'lieu'|'ngay'} p.basis   mg/kg cho MỖI LIỀU hay cho CẢ NGÀY
 * @param {number} [p.dosesPerDay]  số lần/ngày
 * @param {number} [p.maxDoseMg]    trần mỗi liều (mg)
 * @param {number} [p.maxDayMg]     trần mỗi ngày (mg)
 * @param {number} [p.maxMgKgDay]   trần mg/kg/ngày
 * @param {number} [p.concMg]       nồng độ dạng lỏng: concMg mg trong concMl mL
 * @param {number} [p.concMl]
 */
export function tinhLieu(p) {
  const w = num(p.weightKg);
  const mgkg = num(p.mgPerKg);
  const doses = num(p.dosesPerDay);
  const errors = [];
  if (!w) errors.push('Chưa có cân nặng.');
  else if (w < 0.4 || w > 150) errors.push(`Cân nặng ${w} kg nằm ngoài khoảng hợp lý — kiểm tra lại đơn vị.`);
  if (!mgkg) errors.push('Chưa có liều mg/kg.');
  if (p.basis === 'ngay' && !doses) errors.push('Liều tính theo ngày cần số lần dùng mỗi ngày để chia.');
  if (errors.length) return { ok: false, errors, warnings: [] };

  let doseMg;
  let dayMg = null;
  if (p.basis === 'ngay') {
    dayMg = w * mgkg;
    doseMg = dayMg / doses;
  } else {
    doseMg = w * mgkg;
    if (doses) dayMg = doseMg * doses;
  }

  const warnings = [];
  const maxDose = num(p.maxDoseMg);
  const maxDay = num(p.maxDayMg);
  const maxKgDay = num(p.maxMgKgDay);
  if (maxDose && doseMg > maxDose) {
    warnings.push(`Mỗi liều ${roundMg(doseMg)} mg VƯỢT trần ${roundMg(maxDose)} mg/liều.`);
  }
  if (maxDay && dayMg !== null && dayMg > maxDay) {
    warnings.push(`Tổng ngày ${roundMg(dayMg)} mg VƯỢT trần ${roundMg(maxDay)} mg/ngày.`);
  }
  if (maxKgDay && dayMg !== null && dayMg / w > maxKgDay + 1e-9) {
    warnings.push(`Tổng ngày ${roundMg(dayMg / w)} mg/kg VƯỢT trần ${maxKgDay} mg/kg/ngày (= ${roundMg(maxKgDay * w)} mg/ngày với ${w} kg).`);
  }
  if (w >= 40) {
    warnings.push(`Cân nặng ${w} kg: liều theo cân có thể vượt liều người lớn — đối chiếu liều người lớn.`);
  }

  const concMg = num(p.concMg);
  const concMl = num(p.concMl);
  const doseMl = concMg && concMl ? (doseMg * concMl) / concMg : null;

  return {
    ok: true,
    errors: [],
    warnings,
    doseMg: roundMg(doseMg),
    dayMg: dayMg === null ? null : roundMg(dayMg),
    doseMl: roundMl(doseMl),
    dosesPerDay: doses,
    weightKg: w,
  };
}

/** Chuỗi điền vào ô "Liều dùng" / "Thời gian" / "Hướng dẫn" của đơn thuốc. */
export function dienVaoDon(kq, p) {
  const ml = kq.doseMl ? ` (${String(kq.doseMl).replace('.', ',')} mL)` : '';
  const vn = (x) => String(x).replace('.', ',');
  return {
    dosage: `${vn(kq.doseMg)} mg/lần${ml}`,
    frequency: kq.dosesPerDay ? `${vn(kq.dosesPerDay)} lần/ngày` : '',
    note: `Tính theo ${vn(kq.weightKg)} kg × ${vn(num(p.mgPerKg))} mg/kg/${p.basis === 'ngay' ? 'ngày' : 'liều'}`,
  };
}

/**
 * Một liều đọc từ câu Dược thư (backend/pediatric_dose.py) -> giá trị khởi đầu
 * cho các ô. Khoảng liều (10–15 mg/kg) điền ĐẦU DƯỚI: bắt đầu thấp, bác sĩ muốn
 * cao hơn thì tự sửa — không bao giờ để máy chọn đầu trên.
 */
export function tuLieuSach(lieu) {
  return {
    mgPerKg: lieu.mg_kg_min,
    basis: lieu.theo === 'ngay' ? 'ngay' : 'lieu',
    dosesPerDay: lieu.mot_lieu ? 1 : (lieu.so_lan_ngay ? lieu.so_lan_ngay[0] : ''),
    maxDoseMg: lieu.toi_da_mg_lieu || '',
    maxDayMg: lieu.toi_da_mg_ngay || '',
    maxMgKgDay: lieu.toi_da_mg_kg_ngay || '',
  };
}
