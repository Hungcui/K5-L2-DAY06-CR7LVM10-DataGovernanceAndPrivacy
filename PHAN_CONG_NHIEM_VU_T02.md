# KẾ HOẠCH & PHÂN CÔNG NHIỆM VỤ NHÓM CR7LVM10
## Bài Lab Day 06 · Track T02: Raw QC Triage (Ảnh Mờ, Lóa & Thiếu Sáng)

> **Mục tiêu của bài toán:** Xếp hạng ảnh nghi ngờ lỗi (`blur`, `glare`, `dark`, `compression`) để người review trong ngân sách $B=20$ ảnh tìm được nhiều lỗi nhất; đưa ra quyết định cuối cùng **KEEP** hoặc **RECAPTURE**.

---

## 1. TỔNG QUAN PHÂN CHIA VAI TRÒ (4 THÀNH VIÊN)

| Thành viên | Họ tên & MSV | Vai trò | Trọng tâm công việc | File sở hữu chính |
|---|---|---|---|---|
| **Member 1 (Lead)** | Hungcui (2A202604038) | Pipeline Integrator & Risk Owner | Wiring pipeline E2E, quản trị Git, ký duyệt quyết định release (KEEP/RECAPTURE) | `configs/lab.yaml`, `src/pipeline.py` (wiring & decide), `reports/metric_contract.md` |
| **Member 2** | Đỗ Anh Hoàng (2A202604061) | Core Algorithm & Feature Engineer | Code thuật toán phát hiện 4 loại lỗi ảnh, tính điểm tổng hợp `score` | `src/t02_qc.py`, `src/pipeline.py` (hàm `process()`) |
| **Member 3** | Phạm Trung Thành (2A202604050) | QA & Failure Mode Analysis | Viết Unit Tests, phân tích 3 failure cases bắt buộc của T02 | `tests/test_t02_qc.py`, `tests/test_t02_real_samples.py`, `reports/group_report.md` (Mục 06) |
| **Member 4** | Lê Tuấn Anh (2A202604064) | Human Reviewer & Final Report / Demo | Vận hành vòng duyệt người (Contact Sheet HTML), viết báo cáo, làm slide demo | `out/poc/contact_sheet.html`, `reports/group_report.md`, `demo/` |

---

## 2. CHI TIẾT NHIỆM VỤ CHO TỪNG THÀNH VIÊN

---

### 🧑‍💻 MEMBER 1: TEAM LEAD / PIPELINE INTEGRATOR & GOVERNANCE LEAD
* **Mục tiêu:** Đảm bảo toàn bộ hệ thống chạy thông suốt từ đầu đến cuối bằng 1 lệnh duy nhất, quản trị mã nguồn và chịu trách nhiệm pháp lý/governance.
* **File làm việc:** `configs/lab.yaml`, `src/pipeline.py`, `reports/metric_contract.md`.
* **Nhiệm vụ cụ thể:**
  1. **Khóa Metric Contract (30 phút đầu):** Hoàn thiện [reports/metric_contract.md](reports/metric_contract.md) (Primary metric: `Defect Recall@B`, $B=20$, candidate pool: 96 ảnh, đơn vị đánh giá: image).
  2. **Nối dây Pipeline E2E (`src/pipeline.py`):**
     - Hoàn thiện hàm `load()`: Đọc `fixtures/t02_raw_qc/images.csv` và kiểm tra toàn vẹn hash `manifest.csv`.
     - Hoàn thiện hàm `rank()`: Lấy top $B=20$ ảnh có `score` cao nhất đưa vào hàng đợi `review_queue.csv`.
     - Hoàn thiện hàm `decide()`: Trả về đối tượng `Decision(status="KEEP" | "RECAPTURE", reason_code=..., owner="Tên Bạn", evidence=[...])`.
  3. **Quản trị Git & Nộp bài:**
     - Đảm bảo mỗi thành viên có ít nhất 1–2 commit thực chất (`git shortlog -sne --all`).
     - Gắn Git tag trước phút 180 để lấy **+5 điểm bonus**:
       ```bash
       git tag -a demo-180m -m "Demo freeze at minute 180"
       git push origin --tags
       ```
     - Gắn tag nộp bài chính thức trước 24h:
       ```bash
       git tag -a final-24h -m "Final submission"
       git push origin --tags
       ```

---

### 🧠 MEMBER 2: CORE ALGORITHM & FEATURE ENGINEER
* **Mục tiêu:** Xây dựng thuật toán chấm điểm và phát hiện lỗi ảnh vượt trội hơn Baseline ngẫu nhiên/Laplacian đơn thuần.
* **File làm việc:** `src/pipeline.py` (tập trung vào hàm `process(ctx, data)`).
* **Nhiệm vụ cụ thể:**
  1. **Trích xuất đặc trưng cho từng ảnh** (sử dụng thư viện `src/common/image_ops.py`):
     - **Blur (Ảnh mờ):** Dùng `laplacian_variance`. *Lưu ý quan trọng:* Chuẩn hóa theo từng nhóm `camera_id` (tính z-score hoặc chia trung bình của từng cam) vì `cam_B` có ống kính mềm hơn `cam_A` — tránh phạt oan `cam_B`!
     - **Glare (Cháy sáng / lóa đèn / biển số):** Đo diện tích pixel bão hòa `frac_saturated = (gray > 245).mean()`. Có thể chia ảnh thành lưới nhỏ (grid) để phát hiện lóa cục bộ trên biển số.
     - **Dark (Thiếu sáng cực độ):** Đo `frac_dark = (gray < 30).mean()`. Cần kết hợp với trường `light` (day / dusk / night) để không phạt nhầm ảnh đêm hữu ích.
     - **Compression (Nén vỡ hình):** Đo gradient hoặc độ nhiễu blockiness.
  2. **Tính điểm tổng hợp (`score`):**
     - Kết hợp các đặc trưng trên thành một cột điểm số `score` (số thực, giá trị càng cao thể hiện ảnh càng nghi ngờ có lỗi, cần ưu tiên xem xét trước).
     - Gán nhãn dự đoán `pred_defect_type` (`blur`, `glare`, `dark`, `compression`, hoặc `none`).
  3. **Output bắt buộc:**
     - Trả về DataFrame có đủ các cột: `image_id`, `score`, `pred_defect_type`, `reason`.
* **Lệnh chạy kiểm tra:**
  ```bash
  python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
  ```

---

### 🧪 MEMBER 3: QA, UNIT TESTS & PHÂN TÍCH FAILURE MODES
* **Mục tiêu:** Đảm bảo mã nguồn tin cậy, không lỗi và phân tích sâu 3 Failure Modes bắt buộc theo yêu cầu đề bài.
* **File làm việc:** `tests/test_t02_qc.py`, `reports/group_report.md` (Mục 06).
* **Nhiệm vụ cụ thể:**
  1. **Viết Unit Tests trong `tests/test_t02_qc.py`** (ít nhất 2 tests):
     - *Test 1 (Success):* Kiểm tra pipeline chạy thành công với lệnh một dòng, tạo ra file `out/poc/ranked_review.csv` có đầy đủ 2 cột bắt buộc `image_id` và `score`, không chứa giá trị NaN.
     - *Test 2 (Reproducibility & Edge):* Kiểm tra tính tái lập khi chạy với `--seed 42` (2 lần chạy phải cho kết quả giống hệt nhau từng dòng); kiểm tra pipeline không bị crash khi gặp ảnh rỗng hoặc metadata thiếu cột.
     - Chạy lệnh kiểm tra:
       ```bash
       pytest -q tests/test_t02_qc.py
       ```
       *(Bắt buộc đạt 0 failed).*
  2. **Phân tích 3 Failure Modes bắt buộc của T02:**
     - Mở xem trực tiếp các ảnh trong thư mục `fixtures/t02_raw_qc/images/`:
       - *Case 1 (False Reject ở ảnh đêm):* Ảnh ban đêm hợp lệ, rõ ràng nhưng toàn ảnh tối nên dễ bị thuật toán lọc nhầm.
       - *Case 2 (Missed Local Glare):* Ảnh sắc nét toàn cảnh nhưng vùng biển số bị cháy lóa đèn pha bị thuật toán bỏ qua nếu chỉ tính trung bình toàn ảnh.
       - *Case 3 (Camera Bias):* Ảnh từ `cam_B` bị đánh tụt điểm chỉ vì quang học ống kính mềm hơn `cam_A`.
     - Chụp ảnh minh họa, ghi rõ `image_id` và giải thích nguyên nhân gốc rễ (Root Cause) vào **Mục 06** của file [reports/group_report.md](reports/group_report.md).

---

### 📋 MEMBER 4: HUMAN REVIEWER & FINAL REPORT / DEMO
* **Mục tiêu:** Vận hành vòng lặp người duyệt (Human-in-the-Loop), tạo audit trail minh bạch, hoàn thiện báo cáo và slide thuyết trình.
* **File làm việc:** `out/poc/contact_sheet.html`, `reports/group_report.md`, `reports/team_contributions.csv`, thư mục `demo/`.
* **Nhiệm vụ cụ thể:**
  1. **Thực hiện Human Review:**
     - Khi Member 1 & 2 chạy xong pipeline, mở file `out/poc/contact_sheet.html` bằng trình duyệt web (hoàn toàn offline).
     - Nhập tên của bạn vào ô Reviewer.
     - Xem xét 20 ảnh trong hàng đợi review top-B, chọn quyết định (`approve/reject/edit/escalate`), điền ghi chú lý do.
     - Bấm nút **Export CSV** để tải file `review_queue_reviewed.csv`.
     - Đặt file này vào `out/poc/review_queue_reviewed.csv` và báo Member 1 chạy lại pipeline để sinh file lịch sử kiểm toán `out/poc/audit_log.jsonl`.
  2. **Hoàn thiện Báo cáo [reports/group_report.md](reports/group_report.md):**
     - Điền Header (Mục 00), Problem statement (Mục 01).
     - Điền bảng thông số kỹ thuật máy chạy, latency ms/ảnh từ file `out/poc/run_info.json`.
     - Điền bảng phân chia đóng góp trong [reports/team_contributions.csv](reports/team_contributions.csv).
  3. **Làm Slide thuyết trình (3–5 slide trong `demo/`):**
     - Slide 1: Giới thiệu nhóm CR7LVM10 & Bài toán T02 Raw QC Triage.
     - Slide 2: Kiến trúc Pipeline 5 bước + Thuật toán phát hiện lỗi đa chiều.
     - Slide 3: Vòng lặp Human-in-the-loop (Ảnh chụp Contact Sheet + Audit Log).
     - Slide 4: Phân tích 3 Failure Cases & Quyết định phát hành (KEEP / RECAPTURE).

---

## 3. CÁC LỆNH KIỂM CHUẨN CẦN CHẠY TRƯỚC KHI NỘP

```bash
# 1. Kiểm tra môi trường (yêu cầu 0 FAIL)
python -m tools.preflight
python -m tools.verify_manifests

# 2. Chạy baseline
python -m src.main --track t02 --pipeline src.examples.random_baseline --output out/baseline --run-name baseline --offline --seed 42

# 3. Chạy pipeline PoC chính thức của nhóm
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

# 4. Chạy toàn bộ bộ test (yêu cầu 0 failed)
pytest -q
```

---

## 4. TIÊU CHÍ ĐẠT ĐIỂM TỐI ĐA (RUBRIC 100 ĐIỂM + 15 ĐIỂM THƯỞNG)

- **22đ:** Chạy 1 lệnh duy nhất ra kết quả, đủ 5 bước, output đúng chuẩn (`ranked_review.csv`).
- **18đ:** Khai báo metric trung thực, đúng hợp đồng (`metric_contract.md`).
- **18đ:** So sánh công bằng với Baseline (cùng seed 42, cùng budget B=20).
- **12đ:** Human-in-the-loop hoàn chỉnh: có Contact Sheet HTML, có `review_queue_reviewed.csv`, sinh được `audit_log.jsonl`, Decision có `owner` và `reason_code`.
- **12đ:** Có ít nhất 2 unit tests của nhóm (pass 100%), phân tích rõ ràng 3 failure cases.
- **10đ:** Báo cáo đầy đủ, mỗi thành viên đều có commit thực chất trên Git.
- **8đ:** Showcase và trả lời phản biện xuất sắc.
- **+15đ Bonus:** Tag Git `demo-180m` trước phút 180 (+5đ), có phân tích ablation/held-out (+5đ), phản biện tìm ra bug thật bằng test (+5đ).
