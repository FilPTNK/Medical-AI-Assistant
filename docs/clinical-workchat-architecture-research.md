# Nền tảng Workchat cho Trợ lý Fil

Cập nhật ngày 11/11/2026, giờ Việt Nam.

## Màn hình tham chiếu

Ảnh IDEAS do người dùng cung cấp cho thấy màn hình khởi động toàn trang. Robot là điểm nhìn chính, bao quanh bởi các vòng quỹ đạo và điểm sáng trên nền đỏ sẫm. Tên sản phẩm, thanh tiến trình và thông báo nằm ngay dưới robot. Kết quả kiểm tra URL công khai vẫn chưa xác nhận được giao diện sau khi đăng nhập. Công cụ web báo không truy cập được trang, tìm kiếm trên tên miền IDEAS chưa tìm thấy trang Workchat và trình duyệt tích hợp gặp lỗi khởi tạo trước khi mở URL. [Trang IDEAS được cung cấp](https://myerp-stagging.ideas.edu.vn/).

Fil đã có lớp khởi động trong `frontend/index.html`. Có thể giữ bố cục tập trung của ảnh tham chiếu và dùng nhận diện Fil, quỹ đạo nhẹ, trạng thái ngắn cùng hai chế độ sáng và tối. Giữ thanh tải không xác định nếu máy chủ chưa cung cấp phần trăm thật. Dòng hiện tại chuyển sang “Đang nạp mô hình tra cứu y văn…” sau sáu giây, trong khi `window.__bootDone()` chạy khi `Website` đã render và chưa theo dõi tiến độ nạp mô hình. Dùng trạng thái trung tính trong khoảng chờ này, cập nhật bằng sự kiện thực nếu có và kết thúc khi giao diện sẵn sàng. Giữ thông báo đọc được bằng trình đọc màn hình và phiên bản tĩnh khi người dùng giảm chuyển động. [Màn hình khởi động](../frontend/index.html), [Điểm kết thúc](../frontend/src/Website.jsx), [W3C Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

## Thiết kế và xem trước

UI/UX Pro Max phù hợp để rà cấu trúc chat, khả năng đọc, kích thước nút, trạng thái chờ và bố cục hẹp. Frontend-design phù hợp để áp dụng nhận diện Fil vào màn hình khởi động và vùng hội thoại. Polish dùng cho bước kiểm tra cuối. Cả ba đã có trên máy. [UI/UX Pro Max](<C:/Users/HP/.codex/skills/ui-ux-pro-max/SKILL.md>), [Frontend-design](<C:/Users/HP/.codex/skills/frontend-design/SKILL.md>), [Polish](<C:/Users/HP/.codex/skills/polish/SKILL.md>).

Dùng React, Radix, Lucide và Be Vietnam Pro hiện có cho vùng nhập câu hỏi, lịch sử và thẻ nguồn. Frontend đã cấu hình lệnh dev, build và preview của Vite cùng bộ kiểm thử Vitest. Cấu hình dev chuyển tiếp `/api` tới backend tại `127.0.0.1:8000`. Các thành phần này đủ để dựng và kiểm tra giao diện trong repo. Kiểm tra trình duyệt có thể dùng backend cục bộ với dữ liệu giả lập khi công cụ xem trước hoạt động. [Package frontend](../frontend/package.json), [Cấu hình Vite](../frontend/vite.config.js), [Tài liệu Vite](https://vite.dev/guide/).

## Kỹ thuật áp dụng cho Fil

| Kỹ thuật được đề xuất | Áp dụng vào Trợ lý Fil |
| --- | --- |
| Ngữ cảnh động và phân quyền | Lấy người dùng từ phiên Bearer đã xác thực. Đưa vai trò, ngữ cảnh chuyên môn cần thiết và khả năng hiện có vào lời nhắc. Mỗi truy vấn dữ liệu kiểm tra quyền của người dùng ở backend. |
| Function calling | Công bố ít công cụ, có tên, tham số bắt buộc, kiểu, giới hạn và hợp đồng kết quả rõ ràng. |
| Thực thi đơn định | Mỗi công cụ ánh xạ tới hàm Python cố định với truy vấn tham số hóa. Phạm vi đầu tiên gồm đọc trạng thái và đọc nguồn được cấp quyền. |
| Trạng thái và thẻ giao diện | Lưu hội thoại theo chủ tài khoản. React hiển thị văn bản, trạng thái và trích dẫn từ các kiểu dữ liệu đã kiểm tra. |
| Kiểm soát rủi ro | Áp dụng giới hạn kích thước, thời gian, số lượt gọi và danh sách công cụ. Xác thực đầu vào, lọc trường đầu ra theo ngữ cảnh hiển thị và hạn chế dữ liệu gửi ra dịch vụ mô hình. |

Fil đã có `authenticate` và `current_user` để xác thực phiên, `can_view` để phân quyền tài liệu, và client DeepSeek tương thích OpenAI. `web_tools.py` đã có ví dụ khai báo công cụ. Dùng cấu hình URL và mô hình hiện tại để giữ tương thích với triển khai đang chạy. [Xác thực hiện có](../backend/main.py), [Quyền tài liệu](../backend/documents.py), [Cấu hình](../backend/config.py), [Client mô hình](../backend/llm_client.py), [Khai báo công cụ hiện có](../backend/web_tools.py).

## Hợp đồng công cụ và dữ liệu nguồn

Một registry nhỏ có thể bắt đầu với công cụ đọc trạng thái kho tài liệu. Khi có tài liệu đã duyệt, bổ sung tìm kiếm theo `query` và `limit` đã giới hạn. Backend truyền người dùng đã xác thực trực tiếp vào hàm thực thi. Chỉ những tham số nghiệp vụ cần cho truy vấn mới xuất hiện trong schema. Pydantic strict mode và `extra="forbid"` kiểm tra kiểu dữ liệu và trường thừa. Việc thực thi chạy qua hàm cố định với câu truy vấn SQL tham số hóa. Tầng MDL có thể được cân nhắc nếu về sau cần cho người dùng truy vấn một mô hình dữ liệu quan hệ phức tạp. [FastAPI Get Current User](https://fastapi.tiangolo.com/tutorial/security/get-current-user/), [Pydantic Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), [Pydantic extra](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.extra), [SQLite parameter binding](https://docs.python.org/3/library/sqlite3.html#how-to-use-placeholders-to-bind-values-in-sql-queries).

DeepSeek dùng một tin nhắn trợ lý chứa lời gọi công cụ, rồi một kết quả tương ứng với từng `tool_call_id`. Backend kiểm tra tên và đối số, thực thi công cụ trong ngân sách giới hạn và gửi kết quả về mô hình để hoàn tất câu trả lời. Chế độ schema strict của nhà cung cấp dùng endpoint Beta riêng. Kiểm tra Pydantic ở máy chủ phù hợp với client ổn định hiện có và vẫn cần thiết khi mô hình đề xuất đối số. [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/).

Mô hình và nội dung tài liệu đi qua các điểm kiểm tra quyền và tham số như đầu vào ứng dụng thông thường. Bộ lọc câu chữ hỗ trợ phát hiện mẫu đã biết. Quyền truy cập do backend quyết định. Dùng dữ liệu JSON đã kiểm tra để chọn component React và các khóa nguồn do server trả về. Markdown có thể dùng renderer hiện có, với cấu hình kiểm soát link và tải ảnh ngoài. [OWASP Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html), [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/), [OWASP Improper Output Handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/), [react-markdown Security](https://github.com/remarkjs/react-markdown#security).

Hiện người dùng sẽ cung cấp tài liệu ở một lượt sau. Adapter kho tri thức có thể trả trạng thái chưa sẵn sàng và danh sách nguồn rỗng. Chat với mô hình đã cấu hình vẫn có thể hỗ trợ hội thoại và soạn nháp từ nội dung người dùng cung cấp. Giao diện ghi rõ trạng thái nguồn để bác sĩ biết mức đối chiếu hiện có. Kho đã nạp trong các tính năng cũ có phạm vi sử dụng riêng. Khi có bộ tài liệu được duyệt cho Workchat, lọc tài liệu theo quyền trước khi lấy đoạn trích, gắn mỗi trích dẫn với `doc_name` và số trang thật, rồi kiểm tra lại quyền khi mở trình đọc. `ChatDocuments` và `PageViewer` là hai điểm có thể tái sử dụng cho tài liệu và trích dẫn. [Danh mục và quyền nguồn](../backend/documents.py), [Danh sách nguồn](../frontend/src/components/ChatDocuments.jsx), [Trình đọc trang](../frontend/src/components/PageViewer.jsx).

## Hội thoại và giao diện phản hồi

DeepSeek Chat Completions nhận lại ngữ cảnh hội thoại trong mỗi lần gọi. Lưu phiên Workchat theo chủ tài khoản ở backend và lấy cửa sổ hội thoại gần nhất theo cặp chủ sở hữu và ID hội thoại. Giữ thứ tự các lượt và một khóa chống gửi trùng cho mỗi yêu cầu. Lịch sử cũ trong `med_conversations` thuộc bộ nhớ trình duyệt. Dùng hệ thống mới cho các lượt Workchat để bảo đảm truy vấn hội thoại có kiểm tra quyền. [DeepSeek Multi-round Conversation](https://api-docs.deepseek.com/guides/multi_round_chat/), [Lịch sử trình duyệt hiện có](../frontend/src/components/useClinicalData.js).

Giao diện hiện có điểm nối sẵn cho câu hỏi, trạng thái và nguồn. `apiClient.js` gắn Bearer token vào API cùng origin và `readSseStream` đọc sự kiện UTF-8 từ phản hồi POST. Có thể dùng chúng cho lời đáp, trạng thái công cụ và trích dẫn có kiểu rõ ràng. Khi kho chưa sẵn sàng, hiển thị trạng thái chờ tài liệu. Khi tra cứu trả về nhiều kết quả, hiển thị danh sách hoặc câu hỏi làm rõ. Chi tiết một nguồn phải dựa trên kết quả của backend. [API client](../frontend/src/lib/apiClient.js), [SSE client](../frontend/src/lib/sse.js), [Màn hình hỏi đáp hiện có](../frontend/src/App.jsx).

Kiểm tra với mô hình giả lập và hai tài khoản thử. Xác minh quyền đọc từng hội thoại, kiểm tra schema và giới hạn vòng gọi, xác minh nguồn ở trạng thái chưa có tài liệu, giữ đúng thứ tự lượt sau khi tải lại, và hiển thị được thẻ nguồn từ dữ liệu đã cấp quyền. Kiểm tra màn hình khởi động trên bố cục hẹp, chế độ sáng và tối, và thiết lập giảm chuyển động.

## Đã triển khai trong Fil

- Màn hình khởi động dùng SVG linh vật Fil và CSS cục bộ. Trạng thái chuyển từ tải giao diện sang kiểm tra phiên khi React bắt đầu xác thực; thanh chờ không hiện phần trăm. Hỗ trợ sáng, tối, giảm chuyển động và tải lại nếu chờ lâu.
- API `/api/workchat` dùng phiên đăng nhập sẵn có. Hội thoại trong SQLite được truy cập theo cặp chủ sở hữu và ID. API từ chối trường quyền trong yêu cầu, giới hạn lượt và thời gian xử lý, và dùng mã lượt hỏi để gửi lại mà không ghi trùng. Hội thoại cũ đã gắn tài khoản vẫn mở được từ trình duyệt; chúng không tự chuyển lên máy chủ.
- Hai công cụ hiện có là `search_medical_sources` và `prepare_note_outline`. Hệ thống kiểm tra đối số bằng Pydantic, lọc tài liệu theo tài khoản trước khi tìm và kiểm tra lại nguồn khi lưu hoặc đọc hội thoại. Lượt tra cứu có nguồn mới gửi nội dung cần thiết đến DeepSeek. Mô hình không nhận khóa phiên, email hay quyền thực thi SQL. Phản hồi được kiểm tra số trích dẫn và số liệu có đơn vị; giao diện dùng thẻ và đoạn văn từ JSON đã kiểm tra.
- Khi chưa có tài liệu, câu hỏi tra cứu nhận trạng thái kho trống. Hai khung ghi chú trong nút dấu cộng hoạt động bằng mẫu có sẵn. Khi nguồn đã sẵn sàng mà chưa có khóa AI, Fil vẫn trả về các đoạn trích phù hợp để bác sĩ đọc.
- Tài liệu tải lên từ phần Hỏi đáp y khoa chỉ được mở cho Workchat sau khi nạp chỉ mục xong. Với một tài liệu đã nạp bằng quy trình khác và được duyệt dùng trong Workchat, đặt `WORKCHAT_SOURCE_NAMES` thành danh sách `doc_name` phân cách bằng dấu phẩy. Bộ lọc quyền tài liệu vẫn áp dụng. Bản này chưa đưa bộ tài liệu nào vào kho mới.

Mã triển khai: [luồng Workchat](../backend/workchat.py), [API](../backend/workchat_routes.py), [kho hội thoại](../backend/workchat_store.py) và [kiểm thử](../tests/test_workchat.py).

Kiểm tra: 135 bài kiểm thử backend và 19 bài frontend đạt; Vite tạo bản dựng thành công. Bản dựng chạy trên Chromium với tài khoản thử, kho trống và API Workchat thật trên localhost: kiểm tra khởi động sáng/tối, giảm chuyển động ở 375 px, tạo khung ghi chú, tải lại hội thoại, dừng và gửi tiếp. Các lượt có nguồn dùng mô hình giả lập; chưa gọi DeepSeek thật hoặc nạp tài liệu thật trong lần này.
