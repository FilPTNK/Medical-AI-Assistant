import { describe, it, expect } from 'vitest';
import { tinhLieu, dienVaoDon, tuLieuSach, roundMg } from './doseCalc';

describe('Tính liều theo cân nặng', () => {
  it('liều mỗi lần × cân nặng, kèm tổng ngày và mL theo nồng độ', () => {
    // Paracetamol 15 mg/kg × 12 kg, 4 lần/ngày, siro 250 mg/5 mL
    const kq = tinhLieu({ weightKg: 12, mgPerKg: 15, basis: 'lieu', dosesPerDay: 4, concMg: 250, concMl: 5 });
    expect(kq.ok).toBe(true);
    expect(kq.doseMg).toBe(180);
    expect(kq.dayMg).toBe(720);
    expect(kq.doseMl).toBe(3.6);
    expect(kq.warnings).toEqual([]);
  });

  it('liều theo ngày được chia đều cho số lần', () => {
    // Cefuroxim 75 mg/kg/ngày chia 3 lần, 10 kg
    const kq = tinhLieu({ weightKg: 10, mgPerKg: 75, basis: 'ngay', dosesPerDay: 3 });
    expect(kq.doseMg).toBe(250);
    expect(kq.dayMg).toBe(750);
  });

  it('báo vượt trần nhưng KHÔNG tự cắt liều', () => {
    // Azithromycin 30 mg/kg, trần 1,5 g, trẻ 60 kg
    const kq = tinhLieu({ weightKg: 60, mgPerKg: 30, basis: 'lieu', dosesPerDay: 1, maxDoseMg: 1500 });
    expect(kq.doseMg).toBe(1800);
    expect(kq.warnings.some(w => w.includes('VƯỢT trần 1500'))).toBe(true);
    expect(kq.warnings.some(w => w.includes('liều người lớn'))).toBe(true);
  });

  it('trần mg/kg/ngày tính trên tổng ngày', () => {
    const kq = tinhLieu({ weightKg: 10, mgPerKg: 20, basis: 'lieu', dosesPerDay: 4, maxMgKgDay: 60 });
    expect(kq.dayMg).toBe(800);
    expect(kq.warnings[0]).toContain('80 mg/kg VƯỢT trần 60 mg/kg/ngày');
    // Đúng bằng trần thì không báo
    expect(tinhLieu({ weightKg: 10, mgPerKg: 15, basis: 'lieu', dosesPerDay: 4, maxMgKgDay: 60 }).warnings).toEqual([]);
  });

  it('từ chối thiếu dữ kiện và cân nặng vô lý thay vì tính bừa', () => {
    expect(tinhLieu({ weightKg: '', mgPerKg: 15, basis: 'lieu' }).ok).toBe(false);
    expect(tinhLieu({ weightKg: 12, mgPerKg: 20, basis: 'ngay' }).errors[0]).toContain('số lần');
    expect(tinhLieu({ weightKg: 1200, mgPerKg: 15, basis: 'lieu' }).ok).toBe(false);   // gõ gram thay kg
    expect(tinhLieu({ weightKg: '12,5', mgPerKg: '7,5', basis: 'lieu' }).doseMg).toBe(94);
  });

  it('làm tròn: dưới 10 mg giữ một số lẻ', () => {
    expect(roundMg(3.456)).toBe(3.5);
    expect(roundMg(93.75)).toBe(94);
  });

  it('chuỗi điền vào đơn dùng dấu phẩy thập phân', () => {
    const p = { weightKg: 12.5, mgPerKg: 7.5, basis: 'lieu', dosesPerDay: 3, concMg: 120, concMl: 5 };
    const d = dienVaoDon(tinhLieu(p), p);
    expect(d.dosage).toBe('94 mg/lần (3,9 mL)');
    expect(d.frequency).toBe('3 lần/ngày');
    expect(d.note).toBe('Tính theo 12,5 kg × 7,5 mg/kg/liều');
  });

  it('câu sách có khoảng liều thì điền đầu dưới; liều duy nhất là 1 lần', () => {
    expect(tuLieuSach({ mg_kg_min: 10, mg_kg_max: 15, theo: 'lieu', so_lan_ngay: [2, 3], mot_lieu: false,
                        toi_da_mg_kg_ngay: 60 })).toMatchObject({ mgPerKg: 10, dosesPerDay: 2, maxMgKgDay: 60 });
    expect(tuLieuSach({ mg_kg_min: 30, mg_kg_max: 30, theo: 'lieu', so_lan_ngay: null, mot_lieu: true,
                        toi_da_mg_lieu: 1500 })).toMatchObject({ dosesPerDay: 1, maxDoseMg: 1500 });
  });
});
