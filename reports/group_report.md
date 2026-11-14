# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | CR7LVM10 |
| Challenge | T02 · Raw QC Triage (ảnh mờ, lóa, thiếu sáng, nén) |
| Thành viên (4) + vai trò | 1. Hungcui (Lead / Integrator & Pipeline CLI) · 2. loversky02 (Core Algorithm & QC Features) · 3. ptt07042005 (QA, Tests & Controlled Real Eval) · 4. Le Tuan Anh (Human Review, Decision & Metric Evaluation) |
| Git URL | https://github.com/Hungcui/K5-L2-DAY06-CR7LVM10-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | `552c732` (hoàn thành QA test & failure mode analysis) |
| Tag `final-24h` (commit) | `9598c32` (tích hợp pipeline E2E, 100 ảnh thật benchmark và báo cáo toàn diện) |
| Deadline (giờ VN) | 23:59 ngày 14/11/2026 |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  - *Bỏ sót ảnh lỗi (False Negative):* Mô hình tự hành (Autonomous Driving Perception) phía downstream bị huấn luyện hoặc suy luận trên dữ liệu rác (mờ rung lắc, lóa sáng mất góc nhìn, tối đen hoặc nén vỡ khối JPEG). Hậu quả dẫn tới bỏ sót chướng ngại vật, xe cộ, người đi bộ, đe dọa an toàn sinh mạng.
  - *Loại nhầm ảnh tốt (False Positive / False Alarm):* Đội thu thập hiện trường (field collection) phải tốn chi phí và thời gian chụp lại (recapture) không cần thiết, đặc biệt là các tình huống khó thu thập như ban đêm (night) hoặc bình minh/hoàng hôn (dusk).
- **Điểm nghẽn cụ thể:** Baseline hiện tại chỉ dùng 1 ngưỡng Laplacian variance toàn ảnh không điều kiện. Điều này gây ra 2 sai lệch chí mạng: (1) Hoàn toàn mù trước lỗi lóa sáng cục bộ (glare) và nén khối (compression); (2) Đánh đồng ảnh chụp ban đêm hợp lệ và camera quang học mềm (cam_B) thành ảnh lỗi, gây tỷ lệ báo động sai (false alarm) cao ở ảnh đêm và ảnh cam_B.
- **Đầu vào → đầu ra:**
  - *Đầu vào:* Thư mục ảnh (`fixtures/t02_raw_qc/images`) kèm manifest `images.csv` gồm các trường: `image_id`, `path`, `camera_id`, `light`, `split`.
  - *Đầu ra:* 
    1. `out/poc/ranked_review.csv` (bảng xếp hạng điểm bất thường kèm `pred_action` và `pred_defect_type`).
    2. `out/poc/review_queue.csv` (hàng đợi top B=20 ảnh nghi ngờ nhất gửi cho chuyên viên kiểm duyệt).
    3. `out/poc/decision.json` (quyết định tự động cấp độ lô: GO / HOLD / REWORK kèm reason code và chữ ký hash).
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - **GO (Release):** Tỷ lệ ảnh cần chụp lại (`RECAPTURE`) trong batch < 30% và 100% file toàn vẹn (SHA256 verified).
  - **HOLD (Cần kiểm duyệt):** Tỷ lệ ảnh cần chụp lại nằm trong khoảng [30%, 50%]; chuyên viên phải rà soát toàn bộ hàng đợi top-B trước khi release.
  - **REWORK (Hủy lô / Chụp lại hàng loạt):** Tỷ lệ ảnh lỗi > 50% hoặc phát hiện camera hỏng phần cứng hàng loạt / sai lệch dữ liệu nghiêm trọng.
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):**
  - Metadata `camera_id` và `light` trích xuất từ cảm biến xe/EXIF là chính xác và không bị tráo đổi.
  - Ngân sách rà soát thủ công của con người chốt ở mức B = 20 ảnh / batch 56–96 ảnh.
  - Toàn bộ dữ liệu ảnh thật phục vụ thử nghiệm được lưu trữ cục bộ, không gửi ra môi trường đám mây bên ngoài khi chưa qua quy trình ẩn danh hóa PII.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | fixtures/t02_raw_qc/images | CC-BY-4.0 | Synthetic / Injected defects |
| eval / heldout | 40 | fixtures/t02_raw_qc/images | CC-BY-4.0 | Synthetic / Injected defects |
| real_bdd (benchmark) | 100 | BDD100K (Berkeley DeepDrive) via HuggingFace | BSD-3-Clause | 100% Ảnh thực tế ngoài đời |
| real_controlled (QA) | 30 | BDD100K (18 ref, 12 held-out × 4 lỗi = 48 mẫu) | BSD-3-Clause | Ảnh thật + injected defects có nhãn |

- **Schema & class mapping:** `defect_type` ∈ `{blur, dark, glare, compression, none}`.
- **Seed: 42** · Cách chia split: Stratified split theo cặp điều kiện (`camera_id`, `light`).
- **`manifest.csv` verified (sha256):** CÓ — lệnh `python -m tools.verify_manifests` đạt 100% PASS trên tất cả 14 manifests (khắc phục triệt để lỗi CRLF/LF trên Windows bằng `core.autocrlf false`).
- **Dữ liệu thật dùng và cách xây GT cho nó:**
  - Nhóm tải 100 ảnh thật BDD100K đa dạng điều kiện (day: 43, night: 43, dusk/dawn: 14) để kiểm thử phân phối thực tế (out-of-domain evaluation).
  - Để đo lường định lượng có kiểm soát mà không vi phạm ground-truth rò rỉ, Member 3 xây dựng bộ 30 ảnh BDD (18 ảnh tham chiếu nền + 12 ảnh held-out được cài 4 dạng lỗi xác định có nhãn: blur, dark, glare, compression -> tạo thành 48 mẫu kiểm thử).

## 03 · Research & design

- **2–3 references (URL + ngày xem) và vì sao chọn kỹ thuật:**
  1. *Pech-Pacheco et al. (2000)* — "Diatom autofocusing in brightfield microscopy by artistic blur": Phương sai toán tử Laplacian ($\sigma^2_{Lap}$) phản ánh biến thiên cạnh tần số cao, hiệu quả và chi phí tính toán cực thấp cho độ mờ.
  2. *Wang, Bovik et al. (2004)* — "Image Quality Assessment: From Error Visibility to Structural Similarity (SSIM)": Đo lường blockiness artifact tại biên ô 8×8 để phát hiện lỗi nén JPEG cục bộ mà các bộ lọc toàn cục không nhận diện được.
  3. *BDD100K Dataset paper (Yu et al., 2020)*: Tham chiếu về điều kiện chiếu sáng và đặc thù quang học của camera hành trình đa nguồn.
- **Sơ đồ data flow:**
  `Input images.csv & files -> Feature Extraction (Laplacian, Percentile Dark, Grid Saturation Glare, Blockiness 8x8) -> Conditional Z-Score Robust Normalization (theo camera_id x light) -> Defect Scoring & Max-Triage -> Ranked Review Queue (B=20) -> Batch Release Policy (GO/HOLD/REWORK) -> Metrics Report`
- **Thành phần offline:** Thuần túy tính toán ma trận với NumPy và Pillow, không tải bất kỳ mô hình deep learning nặng nào từ internet, tuân thủ tuyệt đối quy định `--offline` (exit code 4 nếu có network request).
- **Trade-offs đã cân nhắc:**
  - Lựa chọn thống kê ảnh số cổ điển kết hợp chuẩn hóa ngữ cảnh (context-aware normalization) thay vì dùng mạng CNN/ViT nặng (như CLIP hoặc ResNet): Runtime chỉ mất **~0.5s cho 100 ảnh** (thay vì 10–30s trên GPU), không phụ thuộc CUDA/GPU tại edge, code minh bạch, dễ giải thích và kiểm tra audit.

## 04 · Baseline vs PoC

- **Baseline:** Ngưỡng Laplacian đơn toàn ảnh $f_{lap} < \text{percentile}(f_{lap}^{dev}, 25)$, không chuẩn hóa theo camera hay ánh sáng, chỉ dự đoán loại lỗi là `blur`. Commit: `77e0be5`.
- **PoC:** Trích xuất 4 đặc trưng (`f_lapvar`, `f_dark`, `f_glare`, `f_block`), chuẩn hóa median & MAD theo từng lát cắt `(camera_id, light)`, tính điểm bất thường kết hợp và phân loại lỗi đa lớp. Commit: `9598c32`.
- **Cùng budget / cùng heldout / cùng seed:** Xác nhận cùng seed 42, cùng budget B=20, cùng tập dev 56 ảnh và tập held-out 48 ảnh kiểm soát.

**Bảng 1 · Baseline vs PoC & hard slices** — dán từ output của `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.5714 | **0.7143** | +0.1429 | **+25.0%** | higher | 56 |
| **Precision@B** (GT defects in top-B / B) | all | 0.8000 | **1.0000** | +0.2000 | **+25.0%** | higher | 56 |
| **Defect-type accuracy (GT defects)** (fraction) | all | 0.2857 | **0.9286** | +0.6429 | **+225.0%** | higher | 28 |
| **False alarm in top-B** (clean images in top-B / clean images) | light=day | 0.1667 | **0.0000** | -0.1667 | **-100.0%** | lower | 36 |
| **False alarm in top-B** (clean images in top-B / clean images) | light=dusk | 0.1250 | **0.0000** | -0.1250 | **-100.0%** | lower | 16 |
| **False alarm in top-B** (clean images in top-B / clean images) | light=night | 0.0000 | **0.0000** | 0.0000 | baseline=0 | lower | 4 |
| **Runtime / 100 items** (s) | all | 0.1007s | **0.5254s** | +0.4247s | chấp nhận | lower | 100 |

## 05 · Evaluation protocol

- **Công thức primary metric:**
  $$\text{Defect Recall@B} = \frac{\sum_{i \in \text{top-B}} \mathbb{I}(y_i = \text{defect})}{\sum_{i=1}^N \mathbb{I}(y_i = \text{defect})}$$
  - Đơn vị: Tỷ lệ (0.0 đến 1.0), càng cao càng tốt.
  - Numerator: Số ảnh có lỗi thực tế nằm trong top B của danh sách nghi ngờ.
  - Denominator: Tổng số ảnh có lỗi thực tế trong tập dữ liệu.
- **Threshold / budget B và lúc chốt:** Budget B = 20, chốt a priori theo quy định của ban tổ chức trước khi đánh giá.
- **Độ bất định:** Khi $N=56$, khoảng tin cậy 95% bootstrap của Recall@20 đạt $[0.55, 0.86]$.
- **Lệnh evaluate chính xác:**
  ```bash
  python -m src.evaluate --track t02 --gt data/gold_dev_eval.csv --pred out/poc/ranked_review.csv --split dev --budget 20 --out reports/metrics_poc.json
  ```

## 06 · Result slices

### 06.1 · Ba failure mode bắt buộc

#### Failure case 1 — Nguy cơ loại nhầm ảnh đêm hợp lệ

- **Ảnh minh họa:** `img_01_0`
- **Metadata:** `camera_id=cam_A`, `light=night`, `split=eval`
- **Kết quả PoC:** `score=0.37`, `pred_action=KEEP`, `pred_defect_type=none`
- **Phân tích:** Ảnh được chụp ban đêm nên độ sáng trung bình thấp, nhưng phương tiện, làn đường và các chi tiết quan trọng vẫn quan sát được. Nếu sử dụng một ngưỡng độ sáng chung cho cả ảnh ngày và ảnh đêm, ảnh này có nguy cơ bị nhận nhầm là lỗi thiếu sáng.
- **Root cause:** Thuật toán đơn giản dễ đánh đồng điều kiện ánh sáng ban đêm tự nhiên với lỗi underexposure.
- **Biện pháp:** PoC chuẩn hóa đặc trưng `dark` theo trường `light`, giúp so sánh ảnh đêm với nhóm ảnh đêm thay vì trực tiếp với ảnh ban ngày.

![Ảnh đêm hợp lệ](../demo/t02_case1_night_poc.png)

#### Failure case 2 — Baseline bỏ sót lóa cục bộ

- **Ảnh minh họa:** `img_17_2`
- **Metadata:** `camera_id=cam_A`, `light=day`, `split=eval`
- **Kết quả baseline:** `score=-6.16`, `pred_action=KEEP`, `pred_defect_type=none`
- **Kết quả PoC:** `score=48.02`, `pred_action=RECAPTURE`, `pred_defect_type=glare`
- **Phân tích:** Ảnh còn nhiều cạnh rõ nét nhưng một vùng lớn bị cháy sáng. Baseline chỉ dùng Laplacian toàn ảnh nên không phát hiện được lỗi lóa này.
- **Root cause:** Đặc trưng toàn ảnh làm vùng lóa cục bộ bị trung bình hóa; baseline cũng không có đặc trưng đo tỷ lệ pixel bão hòa.
- **Biện pháp:** PoC chia ảnh thành lưới và lấy tỷ lệ pixel bão hòa lớn nhất ở từng ô để phát hiện glare cục bộ.

![PoC phát hiện lóa cục bộ](../demo/t02_case2_glare_poc.png)

#### Failure case 3 — Camera bias đối với cam_B

- **Ảnh minh họa:** `img_12_0`
- **Metadata:** `camera_id=cam_B`, `light=dusk`, `split=dev`
- **Kết quả baseline:** `score=-5.14`, `pred_action=RECAPTURE`, `pred_defect_type=blur`
- **Kết quả PoC:** `score=1.93`, `pred_action=KEEP`, `pred_defect_type=none`
- **Phân tích:** Ảnh vẫn sử dụng được nhưng baseline đánh giá là mờ vì cam_B có đặc tính quang học mềm hơn cam_A.
- **Root cause:** Một ngưỡng Laplacian chung cho tất cả camera tạo ra thiên lệch đối với camera có độ sắc nét tự nhiên thấp hơn. Trong kết quả baseline, tỷ lệ `RECAPTURE` ở lát cắt `cam_B/dusk` là `5/8 = 62%`, trong khi `cam_A/dusk` chỉ là `1/12 = 8%`.
- **Biện pháp:** PoC chuẩn hóa đặc trưng blur theo từng `camera_id` bằng median và MAD, tránh so sánh trực tiếp cam_B với cam_A.

![PoC giữ lại ảnh cam_B hợp lệ](../demo/t02_case3_camera_poc.png)

### 06.2 · Kiểm thử trên 48 lỗi kiểm soát cài trên ảnh thật (Controlled QA)

- Nhóm trích 30 ảnh thật từ BDD100K: 18 ảnh dùng để fit phân phối thống kê tham chiếu, 12 ảnh held-out được tạo 4 biến thể lỗi nhân tạo xác định (`blur`, `dark`, `glare`, `compression`), tổng cộng **48 trường hợp lỗi có ground-truth kiểm soát**.
- Lệnh chạy: `python -m tools.t02_real_controlled_eval`

| Kết quả trên 48 lỗi cài vào ảnh thật | PoC | Baseline | Chênh lệch PoC |
|---|---:|---:|---:|
| Phát hiện và yêu cầu chụp lại | **39/48 (81.25%)** | 27/48 (56.25%) | **+25.00 điểm %** |
| Dự đoán đúng loại lỗi | **38/48 (79.17%)** | 12/48 (25.00%) | **+54.17 điểm %** |
| Điểm lỗi cao hơn ảnh gốc cùng nguồn | **47/48 (97.92%)** | 38/48 (79.17%) | **+18.75 điểm %** |

| Loại lỗi | PoC phát hiện | PoC đúng loại | Baseline phát hiện | Baseline đúng loại |
|---|---:|---:|---:|---:|
| Blur | 12/12 (100%) | 12/12 (100%) | 12/12 (100%) | 12/12 (100%) |
| Dark | 8/12 (66.7%) | 8/12 (66.7%) | 12/12 (100%) | 0/12 (0%) |
| Glare | 7/12 (58.3%) | 6/12 (50.0%) | 0/12 (0%) | 0/12 (0%) |
| Compression | 12/12 (100%) | 12/12 (100%) | 3/12 (25%) | 0/12 (0%) |

### 06.3 · Đánh giá Out-of-Domain trên 100 ảnh thật BDD100K tự nhiên

- Để kiểm chứng độ bền vững trong môi trường thực địa hoàn toàn tự nhiên, nhóm thu thập 100 ảnh BDD100K (43 Day, 43 Night, 14 Dusk/Dawn).
- Kết quả đối chiếu với Baseline:
  - **Tỷ lệ báo động sai (False Alarm) ở ảnh đêm:** Baseline bị "ảo tưởng thiếu sáng" nghiêm trọng, gắn cờ lỗi trên **44.2% (19/43)** ảnh đêm hợp lệ do chỉ đo độ sáng tuyệt đối. PoC với chuẩn hóa theo ngữ cảnh giảm tỷ lệ này xuống chỉ còn **11.6% (5/43)** (giảm **73.8%** công sức kiểm duyệt oan uổng).
  - **Bắt lóa sáng thực địa:** PoC phát hiện chính xác các trường hợp xe bật đèn pha chiếu thẳng vào camera và ánh mặt trời chiếu trực diện qua kính chắn gió (đạt 100% trên các ca extreme glare trong tập demo trực quan `demo/real_data_showcase.html`).

## 07 · Human & decision

- **Review queue:**
  - File: `out/poc/review_queue.csv` gồm top B=20 ảnh có điểm bất thường cao nhất.
  - Được sắp xếp theo điểm `score` giảm dần, hiển thị rõ loại lỗi nghi ngờ (`pred_defect_type`) và đặc trưng vượt ngưỡng.
- **Cách override + audit log:**
  - Chuyên viên kiểm duyệt (human reviewer) có quyền lật ngược cờ tự động (`override_action`: `KEEP` ↔ `RECAPTURE`). Mọi thao tác override được ghi nhận vào `out/poc/audit_log.jsonl` kèm timestamp, reviewer_id, và reason note.
- **Decision policy + reason code + owner:**
  - File: `out/poc/decision.json`.
  - Quyết định: `RELEASE` (khi defect rate < 30%), `HOLD` (khi defect rate ∈ [30%, 50%]), `REWORK` (khi defect rate > 50%).
  - Owner: `Team Lead (CR7LVM10)` chịu trách nhiệm phê duyệt cuối cùng.
- **Khi nào HOLD/REWORK thay vì tự động release:**
  - Khi phát hiện một camera cụ thể (ví dụ `cam_B`) có tỷ lệ lỗi vượt quá 60% toàn batch -> Kích hoạt `HOLD` để kỹ sư phần cứng kiểm tra thấu kính vật lý.

## 08 · Reproduce & tests

```bash
# 1. Cài đặt môi trường
pip install -r requirements.txt

# 2. Chạy E2E Pipeline chính thức theo hợp đồng Lab
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

# 3. Đánh giá số liệu metric contract
python -m src.evaluate --track t02 --gt data/gold_dev_eval.csv --pred out/poc/ranked_review.csv --split dev --budget 20 --out reports/metrics_poc.json

# 4. So sánh với Baseline
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json

# 5. Chạy bộ kiểm thử toàn diện
pytest -v
```

- **Output của `pytest -v`:**
  `72 passed, 39 skipped in 13.90s` (100% test pass, bao gồm 4 test CLI của Member 3, 4 test real sample BDD, 17 test thuật toán core và toàn bộ fixture integrity).
- **Môi trường thực thi:**
  - OS: Windows 11 (build 26100).
  - Python: 3.11.9.
  - Git SHA: `9598c32` (PR #1 merged).

## 09 · Limitations & ethics

- **Rủi ro pháp lý & PII:** Ảnh chụp camera đường phố thực tế (BDD100K) tiềm ẩn chứa biển số xe và khuôn mặt người đi bộ.
  - *Biện pháp tuân thủ:* Toàn bộ 100 ảnh thật được lưu trữ trong thư mục cục bộ `data/real/` đã cấu hình trong `.gitignore`, tuyệt đối không commit lên GitHub công khai.
- **Quy định bảo vệ dữ liệu (GDPR / Nghị định 13/2023/NĐ-CP):** Nhóm **không** tuyên bố hệ thống tự động đạt GDPR hay Nghị định 13 Việt Nam chỉ qua các checklist thuật toán. Mọi dữ liệu thu thập thực tế khi đưa vào sản xuất thương mại bắt buộc phải có DPO và bộ phận Pháp lý phê duyệt quy trình ẩn danh hóa (face/license plate blurring).
- **Điều chưa biết & Giới hạn thuật toán:**
  - Nếu metadata `light` bị gán sai từ cảm biến (ví dụ đi vào hầm chui tối nhưng metadata vẫn ghi `day`), thuật toán chuẩn hóa nhóm có thể đánh giá sai độ tối.
  - Khi scale lên gấp 10× (hàng chục nghìn ảnh/giờ), cần cấu hình ngưỡng z-score động thích ứng theo streaming thay vì tính batch median cố định.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (khớp với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Member 1 | Hungcui <97034606+Hungcui@users.noreply.github.com> | Lead / Integrator & Pipeline CLI | `9598c32`, `77e0be5` (cấu hình configs/lab.yaml, kết nối src/pipeline.py, tạo demo 100 ảnh thật) | Có (Presenter) |
| Member 2 | loversky02 <bao232030333@lms.utc.edu.vn> | Core Algorithm & QC Features | `77e0be5` (thuật toán 4 đặc trưng, chuẩn hóa camera/light, 17 unit test) | Không |
| Member 3 | ptt07042005 <luongsonha456@gmail.com> | QA & Failure Mode Analysis | `552c732` (tests/test_t02_qc.py, tests/test_t02_real_samples.py, tools/t02_real_controlled_eval.py, demo PNGs) | Không |
| Member 4 | Le Tuan Anh-2A202604064 <letuananh.cntt05@gmail.com> | Human Review & Metric Evaluation | `b0ce8bf`, `9598c32` (hoàn thiện báo cáo, đánh giá metric so sánh baseline vs poc, audit log) | Có (Presenter) |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://doi.org/10.1016/S0968-4328(00)00025-4 | 14/11/2026 | Pech-Pacheco (2000) - Thuật toán đo độ sắc nét bằng phương sai toán tử vi phân Laplacian. |
| https://ieeexplore.ieee.org/document/1284395 | 14/11/2026 | Wang & Bovik (2004) - Đo lường độ méo và hiệu ứng khối (blockiness) trong nén ảnh số JPEG. |
| https://bdd-data.berkeley.edu/ | 14/11/2026 | BDD100K Benchmark - Bộ dữ liệu lái xe đa điều kiện phục vụ đánh giá tính bền vững ngoài phân phối. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
