# Reflection

**Học viên:** Dương Phương Hiểu — **Khóa:** K4 — **Mã học viên:** 2A202603008

**Which fault types were hardest to catch, and why?**

Các lỗi tinh vi gần biên dao động sạch khó phát hiện nhất. Baseline 3σ bắt tốt
các sai lệch lớn nhưng có thể bỏ sót lỗi nằm trong từng khoảng riêng lẻ. Tôi
kết hợp volume, amount, null rate và freshness bằng khoảng cách tổng hợp;
row/amount được chuẩn hóa bằng nửa độ rộng dải baseline. Feature skew dùng
ngưỡng 0.65 để tránh báo động giả trong vùng dao động sạch đã nêu ở bài lab.
Embedding dùng ngưỡng drift 0.040 và tuổi tài liệu 45 ngày. Lỗi cấu trúc contract
và lineage có bằng chứng trực tiếp từ tool nên dễ phân biệt hơn lỗi thống kê.

Kết quả harness: Practice 50.00 điểm (TPR 100%), Public 46.90 (TPR 97.44%),
Private 32.41 (TPR 64.81%); FPR đều bằng 0%. Kết quả Private cho thấy khả năng
phát hiện lỗi tinh vi còn hạn chế. Báo cáo không cung cấp chẩn đoán chi tiết,
nên không thể quy các lỗi bỏ sót cho một pillar cụ thể.

Đối chiếu lại đủ 120 verdict Practice theo seq với đáp án công khai xác nhận
TP=33, FP=0, FN=0, TN=87. Public đạt high ở cả bốn pillar. Tôi giữ nguyên các
ngưỡng, không chạy dò Private để tinh chỉnh theo điểm.

**What would you change about your cost/coverage tradeoff, if you had another pass?**

Mỗi tham chiếu mới dùng đúng một phép đo; cache trong ctx.state tránh đo lại.
Practice dùng 180/220 credits. Public dùng 240/220, vượt 9.09% và mất khoảng
1.82 điểm vì chi phí. Private không vượt ngân sách. Tôi ưu tiên coverage đầy đủ
thay vì bỏ các sự kiện cuối stream khi hết tiền; lựa chọn này chưa được chứng
minh là tối ưu khi có một trần chi phí cứng.

Nếu có lượt cải tiến, tôi sẽ thử ước lượng median/MAD online theo từng nhóm
để tách dao động tự nhiên khỏi sai lệch nhẹ, có thời gian khởi động và hạn chế
ảnh hưởng của điểm bất thường lên baseline học được. Tôi sẽ kiểm chứng bằng
stream sạch và lỗi giả lập mới trước khi áp dụng. Khi phải giữ trần chi phí
cứng, cần chính sách phân bổ credit theo độ rủi ro và đánh giá rõ phần TPR bị
mất; không suy ra dữ liệu sạch chỉ vì bỏ qua phép đo. Không dùng đáp án theo
event ID hoặc điều chỉnh ngưỡng bằng cách chạy dò điểm Private.
