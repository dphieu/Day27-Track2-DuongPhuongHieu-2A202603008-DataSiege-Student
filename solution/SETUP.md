# Môi trường và cách chạy Data Siege

## Môi trường Windows PowerShell

Môi trường `.venv` đã được tạo bằng Python 3.11.5. Các dependency đã cài:
`cryptography==50.0.2`, `cffi==2.1.1`, `pycparser==3.11`.
`pip check` không phát hiện dependency bị lỗi.

Chạy từ thư mục gốc repo. Có thể gọi Python trong môi trường ảo trực tiếp,
không cần kích hoạt PowerShell script:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe harness/selfcheck.py
.\.venv\Scripts\python.exe -m unittest discover -s solution -p test_defense.py -v
.\.venv\Scripts\python.exe harness/run.py --phase practice --defense solution/defense.py --out solution/practice_report.json
.\.venv\Scripts\python.exe solution/validate_practice.py
.\.venv\Scripts\python.exe harness/run.py --phase public --defense solution/defense.py --out solution/public_report.json
.\.venv\Scripts\python.exe harness/run.py --phase private --defense solution/defense.py --out solution/private_report.json
```

Mỗi phase chỉ chạy khi key tương ứng đã được phát hành. Dùng harness để chạy;
không đọc key hoặc tự giải mã schedule. Không sửa nội dung báo cáo đã ký.

## Cấu trúc và phạm vi chỉnh sửa

| Đường dẫn | Vai trò |
| --- | --- |
| `solution/defense.py` | `register(ctx)` và 5 handler phát hiện lỗi trực tuyến |
| `solution/test_defense.py` | Kiểm tra bằng phép đo giả lập, không dùng dữ liệu phase |
| `solution/validate_practice.py` | Đối chiếu offline theo `seq` với đáp án Practice công khai |
| `solution/practice_validation.json` | Ma trận nhầm lẫn và các verdict sai của Practice |
| `solution/reflection.md` | Phân tích độ khó và đánh đổi chi phí |
| `solution/*_report.json` | Kết quả do harness tạo và ký |
| `data/baselines.json` | Các ngưỡng công khai, được cung cấp qua `ctx.baseline` |
| `docs/TOOLKIT_API.md` | API tool, chi phí và dữ liệu trả về |
| `harness/selfcheck.py` | Kiểm tra import và đăng ký handler |
| `harness/run.py` | Chạy stream, sandbox và chấm điểm |
| `submission/manifest.json` | Thông tin nộp bài, điền theo danh tính người học |

Theo `RULES.md`, chỉ sửa nội dung bài nộp trong `solution/` và `submission/`.
`.venv` và Python cache đã được gitignore. Harness và baseline giữ nguyên.

## Thiết kế detector

- `data_batch`: kiểm tra volume, null, mean amount, freshness và khoảng cách
  tổng hợp. Tâm row/amount là trung điểm baseline; mẫu số là nửa độ rộng dải
  baseline (3σ). Ngưỡng khoảng cách là `1.30` theo đơn vị này. Nếu đổi mẫu số
  sang 1σ thì phải hiệu chuẩn lại ngưỡng, không giữ nguyên `1.30`.
- `contract_checkpoint`: phát hiện violation và kiểm tra freshness theo giới hạn
  nhỏ hơn giữa SLA khai báo và baseline.
- `lineage_run`: phát hiện output không có downstream, thiếu `raw.orders` hoặc
  `raw.customers`, và runtime vượt baseline. Hai upstream này là yêu cầu của
  model orders trong lab; cần cấu hình lại nếu mở rộng sang model khác.
- `feature_materialization`: ngưỡng `mean_shift_sigma > 0.65`.
- `embedding_batch`: ngưỡng `centroid_shift > 0.040` hoặc tuổi tài liệu `> 45` ngày.

Mỗi tham chiếu mới gọi một tool tính phí. Kết quả được lưu trong `ctx.state`
để không trả phí lại khi cùng tham chiếu xuất hiện lần nữa trong một run.
Cache giả định phép đo của một batch/run đã định danh không thay đổi.
Tool trả về `error` sẽ tạo verdict không cảnh báo, `confidence=0`, kèm lý do
thiếu phép đo; verdict đó không khẳng định dữ liệu đã được kiểm tra là sạch.

Detector ưu tiên kiểm tra đầy đủ, không tự ngừng đo khi hết credit. Với stream
Public hiện tại, lựa chọn này vượt 20 credits và chịu phạt khoảng 1.82 điểm.
Không thể bảo đảm đồng thời kiểm tra đầy đủ và giữ chi phí dưới 220 nếu mọi
sự kiện đều cần phép đo trả phí và không có tham chiếu trùng để dùng cache.
Chiến lược hiện tại chưa được chứng minh là tối ưu toàn cục.

## Sandbox

`defense.py` chỉ import `Verdict` từ `api`; không dùng dependency bên thứ ba,
file I/O hoặc `print()`. Stdout dành riêng cho JSON-RPC. Trạng thái qua các sự
kiện nằm trong `ctx.state` và không tồn tại sau khi kết thúc run.

Selfcheck chỉ kiểm tra cấu trúc. Bộ 12 test kiểm tra các nhánh phát hiện lỗi,
nhiễu sạch, lỗi tổng hợp, lỗi tool, SLA và cache. Các phase đã chạy thành công
qua child process của harness để kiểm chứng sandbox và IPC thực tế.

## Kết quả của phiên bản hiện tại

| Phase | Score | TPR | FPR | Cost overage | Chi phí / budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Practice | 50.00 | 100% | 0% | 0% | 180 / 220 |
| Public | 46.90 | 97.44% | 0% | 9.09% | 240 / 220 |
| Private | 32.41 | 64.81% | 0% | 0% | Báo cáo không công bố |

Đã chạy lại Practice và Public, giữ nguyên detector và các ngưỡng. Đối chiếu
Practice với `phases/practice_answer_key.json` xác nhận đủ 120 sự kiện:

| Nhãn thực tế | Cảnh báo | Không cảnh báo |
| --- | ---: | ---: |
| Có lỗi | TP = 33 | FN = 0 |
| Sạch | FP = 0 | TN = 87 |

Script đối chiếu ghép bằng `seq`, từ chối ID trùng/thiếu, kiểm tra kiểu boolean,
và tính lại TPR, FPR, overage, score để so với báo cáo. File validation là
chẩn đoán offline, không phải báo cáo có chữ ký và không xác minh chữ ký.
Danh sách `mismatches` hiện rỗng. Không cần tinh chỉnh ngưỡng từ Practice.
Public đạt `high` cho cả `checks`, `contracts`, `lineage`, `ai_infra`.

Khi chi phí giữ nguyên, thay đổi điểm là `50 × ΔTPR − 30 × ΔFPR`.
Vì vậy FPR = 0% không tự động bảo đảm điểm tối ưu: tăng TPR có lợi nếu
`ΔTPR > 0.6 × ΔFPR`. Việc chọn ngưỡng cần bằng chứng trên dữ liệu kiểm chứng
độc lập, không chỉ theo điểm Private. Không bỏ tool để tránh khoản phạt nhỏ
của Public khi chưa đánh giá phần coverage bị mất.

Private cho thấy các ngưỡng hiện tại còn bỏ sót lỗi tinh vi. Không dùng score
Private để dò ngưỡng lặp lại. Bước cải tiến phù hợp là thiết kế thống kê online
robust trên các phép đo được phép, kiểm chứng trên dữ liệu sạch và lỗi giả lập,
sau đó đánh giá trên một stream mới.

## Chuẩn bị nộp

Các file `solution/defense.py`, `solution/reflection.md` và
`solution/private_report.json` đã có sẵn. `submission/manifest.json` đang trỏ
đúng ba file này; `team_or_student` là
`K4-DAY27-DuongPhuongHieu-2A202603008` (Dương Phương Hiểu, khóa K4).

Đã chạy lại cả ba phase bằng harness chính thức để tạo báo cáo có chữ ký.
Cả ba file trùng khớp từng byte với báo cáo trước đó; không sửa thủ công báo cáo
và không đọc key để tự ký kết quả. Selfcheck đạt 5/5 handler, 12 test hành vi
đều đạt. Reflection đã điền tên, khóa, mã học viên và các phân tích cá nhân.

Gói nộp VLearn là
`submission/K4-DAY27-DuongPhuongHieu-2A202603008.zip`, có cấu trúc:

```text
K4-DAY27-DuongPhuongHieu-2A202603008/
├── solution/
│   ├── defense.py
│   ├── reflection.md
│   ├── practice_report.json
│   ├── public_report.json
│   └── private_report.json
└── submission/
    └── manifest.json
```

Nội dung sáu file trong ZIP được đối chiếu từng byte với file nguồn trước khi
commit. Repo GitHub giữ nguyên `solution/` và `submission/` ở thư mục gốc để
harness chạy theo đường dẫn quy định; thư mục mang tên học viên nằm trong ZIP.
