# Tham chiếu Gemini Notebook cho homepage Fil

Ngày khảo sát: **10/11/2026**. Phạm vi: homepage, thanh điều hướng chung, thẻ chuyên khoa và tính nhất quán với trang hỏi đáp. Không thay đổi hay nghiên cứu nội dung thuốc trong đợt này.

## Kết luận triển khai

Dựng lại cấu trúc giao diện bằng React và CSS trong repo hiện tại. Các thư viện, skill và công cụ kiểm tra cần cho đợt thiết kế này đã có sẵn; **không cần thêm thư viện runtime hoặc plugin để sao chép bố cục**. Đây là kết luận từ việc đối chiếu nhu cầu với những dependency thực tế đã cài, không phải khẳng định rằng Google sử dụng cùng stack.

Giữ nhận diện Fil: logo PNG do người dùng cung cấp, bảng màu teal, văn bản tiếng Việt và ba công cụ hiện có. Mượn cách tổ chức của Gemini Notebook: thanh trên gọn, điều hướng nằm sát thương hiệu, tìm kiếm và thao tác nằm bên phải, bên dưới là danh mục notebook có ảnh bìa. Thẻ ở Fil đại diện cho các chuyên khoa; không dùng thương hiệu Google hoặc chép ảnh bìa tài liệu của Google làm tài sản sản phẩm.

## Nguồn nào đã kiểm tra được

| Nguồn | Bằng chứng và giới hạn |
| --- | --- |
| Ảnh header người dùng đính kèm ngày 10/11 | Tham chiếu trực tiếp cho thứ tự logo → All → My notebooks → Discover → Collections → tìm kiếm → grid/list → thiết lập → tài khoản. Chỉ thấy header, không có toàn bộ homepage hay số đo CSS. |
| [Gemini Notebook](https://notebook.google.com/) | Truy cập công khai trả trang giới thiệu và đăng nhập, không trả DOM dashboard đã đăng nhập. Không thể suy ra CSS chính xác của dashboard từ trang công khai này. |
| [Google công bố Featured Notebooks](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-featured-notebooks/) | Bài viết ngày 14/07/2025 có hình minh họa giao diện danh mục notebook. Dùng để hiểu cách trình bày notebook theo chủ đề; không coi hình năm 2025 là thông số pixel của giao diện năm 2026. |
| [Google Help về public/featured notebooks](https://support.google.com/gemininotebook/answer/16322204?hl=en) | Xác nhận notebook tuyển chọn gom tài liệu theo chủ đề, cho xem nguồn, hỏi đáp và chọn/bỏ chọn nguồn ở cột trái. |
| [Google Help về thêm nguồn](https://support.google.com/gemininotebook/answer/16215270) | Xác nhận có thao tác Add sources ở bên trái và chọn các nguồn muốn đưa vào notebook. |

Ảnh minh họa chính thức được liên kết trực tiếp trong bài Featured Notebooks: [Google-hosted image](https://storage.googleapis.com/gweb-uniblog-publish-prod/images/Featured_Notebook_Header_2096x118.width-200.format-webp.webp). Đây là URL ảnh cỡ nhỏ công cụ đọc web thấy được. Công cụ không dựng được ảnh do máy chủ trả `application/octet-stream`; lấy HTML đầy đủ qua shell gặp lỗi SSL. Không thu được `srcset` độ phân giải cao hay bản dashboard đã xác thực. Các kích thước bố cục do triển khai lựa chọn phải được ghi nhận là điều chỉnh cho Fil, không phải số đo lấy từ Google.

## Ánh xạ sang website Fil

Đây là quyết định thiết kế theo yêu cầu người dùng, không phải tính năng được Google công bố cho Fil:

| Thành phần tham chiếu | Thành phần Fil |
| --- | --- |
| Thương hiệu ở đầu thanh | Logo Fil trong suốt, bấm về `/` |
| All | Trang chủ / Tất cả chuyên khoa |
| My notebooks | Tra cứu thuốc → `/thuoc` |
| Discover | Hỏi đáp y khoa → `/hoi-dap` |
| Collections | Hỗ trợ chẩn đoán → `/chan-doan` |
| Search notebooks | Tìm chuyên khoa trên homepage; nếu dùng trên toàn site cần chỉ rõ đích tìm kiếm |
| Grid/list | Hai cách xem cùng một danh mục chuyên khoa, trạng thái nút rõ ràng |
| Featured notebooks | Thẻ Tim mạch, Tai mũi họng, Hô hấp, Nhi khoa… với ảnh bìa riêng của Fil |
| Avatar/settings | Tài khoản và thiết lập chung hiện có của Fil |

Thanh điều hướng phải dùng chung một component và một quy tắc chiều rộng/lề cho mọi trang. Loại bỏ biến thể khiến riêng hỏi đáp đẩy logo và các nút sang vị trí khác. Điều hướng giữa các URL vẫn là liên kết thực; không gắn `role="tab"` chỉ vì hình thức giống tab. WAI định nghĩa tab là tập các panel nội dung xếp lớp hiển thị luân phiên trong cùng widget. [WAI Tabs Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).

Thẻ chuyên khoa cần mở được một trang hoặc ngữ cảnh hỏi đáp thực tế, không chỉ là hình trang trí. Nếu chưa có nguồn được phân loại theo chuyên khoa, không tự tạo số lượng tài liệu, ngày cập nhật hay lời khẳng định đã được chuyên gia duyệt. Ảnh bìa phục vụ nhận diện chủ đề; không dùng nó để minh họa khẳng định chẩn đoán hay nội dung điều trị.

## Thư viện đã có và cách dùng

Các phiên bản dưới đây đọc từ `frontend/node_modules/*/package.json` trong repo ngày khảo sát. Đây là phiên bản cài tại máy, không phải khuyến nghị nâng cấp lên bản mới nhất.

| Thư viện | Đang cài | Quyết định |
| --- | --- | --- |
| React | 18.3.1 | Giữ nguyên; state cho tìm kiếm, đổi kiểu xem và danh mục. |
| Vite | 5.4.21 | Giữ nguyên pipeline asset và production build. Logo/ảnh có thể đặt trong `public` và tham chiếu bằng URL tuyệt đối từ root. [Vite Assets](https://vite.dev/guide/assets). |
| `@radix-ui/react-dropdown-menu` | 2.1.24 | Dùng cho sắp xếp, menu thẻ và thiết lập. Primitive có quản lý focus, bàn phím và xử lý va chạm vị trí. [Radix Dropdown Menu](https://www.radix-ui.com/primitives/docs/components/dropdown-menu). |
| `@radix-ui/react-tabs` | 1.1.21 | Chỉ dùng nếu có bộ lọc/panel tại chỗ thực sự; không cần thay liên kết điều hướng bằng Tabs. Primitive hỗ trợ điều khiển state và bàn phím. [Radix Tabs](https://www.radix-ui.com/primitives/docs/components/tabs). |
| `lucide-react` | 0.344.0 | Dùng icon grid/list/search/settings theo cùng nét. Icon là component SVG độc lập; chỉ import icon sử dụng. [Lucide React](https://lucide.dev/guide/react). |
| `motion` | 13.1.1 | Đã có; không cần bổ sung GSAP cho thay đổi bố cục đơn giản này. Có thể chỉ dùng CSS cho hover/focus. |
| Vitest | 2.1.9 | Giữ bộ kiểm thử hiện có; kiểm tra thêm hành vi thực khi có logic tìm/lọc mới. |

Không cần Material UI, shadcn, Tailwind hoặc một framework mới chỉ để đạt hình thức này. Đây là lựa chọn triển khai: CSS Grid/Flex và các primitive đã cài đủ đáp ứng danh mục thẻ, thanh trên và menu. Không nâng major version của các package trong một thay đổi giao diện.

## Skills và plugins

Đã xác nhận ba skill sau tồn tại cục bộ:

| Skill | Vai trò | Nguồn gốc tham khảo |
| --- | --- | --- |
| `ui-ux-pro-max` | Rà bố cục, tương tác, responsive, độ tương phản | [Kho của tác giả](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), [manifest cài đặt](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/skill.json) |
| `frontend-design` | Chọn cách thể hiện nhất quán với reference và nhận diện Fil | [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) |
| `web-design-guidelines` | Rà tính khả dụng của giao diện sau khi dựng | [Vercel web-design-guidelines](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) |

Không cài lại hoặc ghi đè các skill đang có. Với máy mới, installer chính chủ UI/UX Pro Max công bố lệnh `npx ui-ux-pro-max-cli init --ai codex`; hệ sinh thái Skills CLI hỗ trợ cài skill từ kho cụ thể và chọn agent. Chỉ chạy khi thực sự thiếu, sau khi đọc nội dung skill. [UI/UX manifest](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/skill.json), [Skills CLI của Vercel](https://github.com/vercel-labs/skills).

Figma plugin không cần cho lần này vì đầu vào là ảnh và trang web, không có Figma file cần đọc. Công cụ browser/computer-use đã có phù hợp để so ảnh và kiểm tra responsive. Một plugin có tên “clone website” không thay thế việc kiểm tra trạng thái UI và xử lý thật các nút.

Google hiện có [Gemini Notebook API](https://developers.google.com/notebook/docs) và [MCP chính thức](https://developers.google.com/notebook/docs/mcp) để quản lý notebook/nguồn của người dùng. API dùng OAuth, không phải API key. Những công cụ này phục vụ tích hợp dữ liệu Google, không cung cấp source code hoặc CSS của dashboard. Vì yêu cầu hiện tại là giao diện Fil, không kết nối chúng hay yêu cầu người dùng cấp quyền Google. [Authentication](https://developers.google.com/notebook/docs/authentication).

## Kiểm tra trước khi bàn giao

Các bước dưới đây là checklist triển khai Fil, không phải số đo hay yêu cầu sao chép từ Google:

- Header cùng lề và vị trí tại `/`, `/thuoc`, `/hoi-dap`, `/chan-doan`; đường dẫn hiện hành có trạng thái rõ.
- Dùng đúng PNG người dùng cung cấp và kiểm tra alpha; bỏ nền trắng do CSS wrapper cũ nếu ảnh đã trong suốt.
- Danh mục có ảnh bìa và tên chuyên khoa đọc được; nội dung của hai kiểu xem giống nhau.
- Tìm kiếm xử lý dấu tiếng Việt, có trạng thái không tìm thấy; nút xóa tìm kiếm hoạt động.
- Nút chỉ có icon có nhãn; menu dùng bàn phím, Escape và trả focus đúng.
- Kiểm tra sáng/tối, mobile và desktop; không tràn ngang, không tách một nút thành hai dòng.
- Giữ quyền tài khoản, nguồn riêng/chung và luồng hỏi đáp hiện có. Không tự tạo dữ liệu y khoa hoặc thống kê nội dung.
- Chạy production build, kiểm thử phù hợp và xem screenshot cuối. Các chỗ chỉ ước lượng từ reference cần đánh giá bằng giao diện thực tế, không tuyên bố “100% pixel-perfect” khi chưa có DOM reference.


## Ghi nhận triển khai tại Fil

- `frontend/src/Homepage.jsx` và `frontend/src/homepage.css`: hàng bốn sổ tay nổi bật có ảnh bìa, danh mục 12 chuyên khoa, tìm không dấu/tiếng Anh, lọc đã lưu, sắp xếp tên, lưới/danh sách. Dấu lưu được ghi theo ID tài khoản vào trình duyệt, không gửi lên máy chủ.
- `frontend/src/Website.jsx`: cùng một header cho mọi URL, đúng thứ tự điều hướng người dùng yêu cầu. Tìm kiếm trong header tìm sổ tay chuyên khoa; khi dùng từ trang công cụ khác, Enter đưa về kết quả ở homepage. Menu bánh răng chứa cài đặt, sáng/tối và thông báo; avatar mở tài khoản chung.
- Logo dùng đúng PNG `Modern Teal Fil Healthcare Logo.png`, chép nguyên byte sang `frontend/public/fil-logo.png`. Component `FilLogo.jsx` hiển thị vùng logo trong ảnh có alpha và bỏ wrapper nền trắng; không vẽ lại hay thay tệp gốc. Chế độ tối hiển thị silhouette sáng để giữ tương phản.
- Bốn ảnh bìa được tạo riêng bằng ImageGen cho Tim mạch, Tai mũi họng, Hô hấp và Thần kinh, không lấy ảnh của Google. Bản WebP trong `frontend/public/notebooks/` giảm dung lượng phục vụ web; các PNG gốc vẫn ở kho ảnh được tạo cục bộ. Đây là ảnh trang trí, không dùng làm sơ đồ giải phẫu hay nguồn y khoa.
- Thẻ mở `/hoi-dap?chuyen-khoa=<id>`. Ngữ cảnh chuyên khoa hiện rõ và đi cùng câu hỏi gửi đến luồng tra cứu; nguồn vẫn là các tài liệu người dùng chọn, chưa có phân loại tài liệu riêng cho từng chuyên khoa. Không tự tạo số nguồn hay ngày cập nhật.
- Không thêm dependency hoặc plugin. Không kết nối tài khoản Google, không thay quyền dữ liệu hay nội dung thuốc.
