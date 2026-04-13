# Backend San TMDT Do gia dung - Nhom 04 
QUY ĐỊNH LÀM VIỆC NHÓM - DỰ ÁN 5_4_TMDT_BACKEND
Tài liệu này quy định các tiêu chuẩn về Git, cấu trúc mã nguồn và quy trình phối hợp cho Nhóm 04 dựa trên các nhánh đã xây dựng.
1. Hệ thống Nhánh Thực tế (Existing Branch Strategy)
Chúng ta tuân thủ nghiêm ngặt các nhánh đã tạo trên Repository để quản lý mã nguồn backend:
Nhánh main:
Trạng thái: Chỉ chứa code đã chạy ổn định, không có lỗi.
Quyền hạn: Chỉ Trưởng nhóm mới được phép push hoặc merge vào đây sau khi đã kiểm tra kỹ.
Nhánh develop:
Trạng thái: Nhánh tích hợp. Mọi tính năng mới sau khi hoàn thành ở nhánh feature sẽ được gộp về đây.
Quy tắc: Code ở đây phải luôn ở trạng thái chạy được (không lỗi cú pháp).
Nhánh feature/initial-setup:
Trạng thái: Nhánh nền tảng (Base branch).
Mục đích: Chứa cấu trúc thư mục MVC, AI core và các file cấu hình kết nối đồng thời MySQL & MongoDB. Các thành viên sẽ lấy code mẫu từ đây để bắt đầu.
Nhánh feature/ten-tinh-nang (và các nhánh feature khác):
Trạng thái: Nhánh làm việc riêng của từng thành viên.
Quy tắc: Tên nhánh phải rõ ràng. Ví dụ: feature/ten-tinh-nang/duc-vnpay, feature/ten-tinh-nang/quang-ai-engine. Tuyệt đối không code chung trên một nhánh feature.
2. Quy tắc Vị trí Đặt Code (MVC & AI Core)
Để đảm bảo tính đa tầng (N-tier) như báo cáo, mọi người phải đặt file đúng vị trí:
Tầng Controller (app/controllers/): Viết logic điều hướng. Ví dụ: nhận yêu cầu đặt hàng, kiểm tra tính hợp lệ rồi gọi tầng Service.
Tầng Model (app/models/):
MySQL: Định nghĩa các bảng cho giao dịch (User, Order, Payment).
MongoDB: Định nghĩa dữ liệu sản phẩm đồ gia dụng và lịch sử click chuột phục vụ AI.
Tầng Service (app/services/): Nơi xử lý các API bên ngoài như VNPAY, MoMo, Giao Hàng Nhanh.
Tầng AI (ai_core/): Nơi xây dựng Recommendation Engine. Dữ liệu đầu vào lấy từ MongoDB, kết quả trả về cho Controller.
Cấu hình (config/): Chứa thông tin kết nối Database. Các thành viên sử dụng biến môi trường từ .env, không được gõ cứng mật khẩu vào code.
3. Quy trình Đẩy Code & Đồng bộ Nhánh
Để các nhánh không bị lệch nhau, thành viên phải thực hiện đúng các bước:
Trước khi code: Chuyển về nhánh của mình và cập nhật code mới nhất từ develop:
git checkout develop
git pull origin develop
git checkout feature/ten-cua-ban
git merge develop
Trong khi code: Thường xuyên commit để tránh mất dữ liệu.
git add .
git commit -m "feat: mô tả tính năng vừa làm"
Khi hoàn thành: Đẩy nhánh lên GitHub và thông báo cho Trưởng nhóm trên Zalo.
git push origin feature/ten-cua-ban
Tạo Pull Request (PR) trên GitHub từ nhánh của bạn vào nhánh develop.
4. Văn hóa Làm việc & Bảo mật
File .gitignore: Đã chặn file .env và thư mục venv/. Tuyệt đối không tìm cách đẩy các file này lên để tránh lộ mật khẩu Database của nhóm.
requirements.txt: Mỗi khi cài thêm thư viện (như pandas, pymongo), thành viên đó phải cập nhật file này ngay bằng lệnh pip freeze > requirements.txt để người khác tải về không bị lỗi.
Xử lý xung đột (Conflict): Nếu khi merge gặp lỗi conflict, thành viên phải cùng Trưởng nhóm ngồi lại để đối chiếu từng dòng code, tránh việc xóa nhầm code của bạn mình.
Trách nhiệm Trưởng nhóm :
Kiểm tra chất lượng code (Code Review) trước khi gộp vào develop.
Định kỳ gộp develop vào main để chốt phiên bản ổn định.
Lưu ý: Mọi thành viên phải đọc kỹ sơ đồ Use Case và Biểu đồ tuần tự trong báo cáo để code đúng logic đã thiết kế.
