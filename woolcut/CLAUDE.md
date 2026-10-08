# WoolCut — prompt → Tripo → Claude tách mảnh một màu → S/M/D FBX

Tool thứ hai, viết ngày 2026-10-01, **độc lập với `primforge/`** (không import, chỉ chép code bảng màu/xuất FBX).
Khác PrimForge ở bước 3: PrimForge tách tự động theo hình học/vết màu (ra mảnh nham nhở); WoolCut để
**Claude nhìn ảnh có lưới toạ độ rồi lập kế hoạch cắt** như hoạ sĩ, Blender chỉ thực thi **nhát cắt mặt phẳng**
(tự dò chỗ thắt hẹp nhất, bịt nắp phẳng) — giống cách bộ gốc chia gấu `BearArt.fbx` (đầu 8 múi, thân 4 múi,
đế cắt cung, mõm/tai khối riêng, mắt/mũi là D).

```
1 Prompt ──► 2 Model ──► 3a prep ──► 3b plan (Claude) ──► 3c cut ──► 3d soát (Claude) ──► 4 export
 Claude CLI   Tripo      khối kín     plan.json            parts.blend    sửa plan.json        out/<Ten>.fbx
```

```bash
python woolcut/run.py prompt [--idea "..."]                       # 1
python woolcut/run.py gen --prompt "..." --name Ten [--yes]       # 2 (không --yes = chỉ ước tính credit)
python woolcut/run.py split --in inbox/Ten_xxxx.glb --name Ten --turn -90 [--min 15 --max 35 --rounds 1]
python woolcut/run.py prep|plan|cut|review --name Ten             # từng bước con của 3
python woolcut/run.py export --name Ten [--in work/Ten/parts_edit.blend]   # 4
```
Panel Blender: `woolcut/__init__.py` (tab "WoolCut"), 4 khung đúng 4 bước, chạy nền bằng `run.py`.
Dòng giao kèo với addon: `MODEL_READY:`, `TURN:`, `PREP_READY:`, `CUT_READY:`, `SPLIT_READY:`, `EXPORT_READY:`.

## 1 prompt (`wc/prompt.py`, `wc/categories.py`, `run.py prompt --kind <dạng> --theme <chủ đề> [--mode image]`)
Danh sách "đừng lặp" lấy 108 FBX gốc ở `D:\BlenderTool\Samples` (trước 2026-10-07 tìm nhầm `D:\BlenderTool\*.fbx`
→ luôn rỗng) + model đã làm (`out/*.fbx` và thư mục `work/`).
Thể loại rút từ ảnh thu nhỏ 108 model gốc (2026-10-02), hai trục — panel có hai ô "Dạng" và "Chủ đề":
- DẠNG (`FORMATS`, mỗi dạng có luật + ví dụ + câu phong cách Tripo): `char` nhân vật chibi (parts), `object` đồ
  vật (object), `food` món ăn (object), `scene` cảnh nhỏ trên đế (multi), `plant` cây & hoa (object).
- CHỦ ĐỀ (`THEMES`, kèm danh sách model gốc cùng chủ đề để Claude theo phong cách, không lặp): tự do, âm nhạc,
  hải tặc, ẩm thực, thời trang & làm đẹp, nhà cửa & đồ dùng, biển & mùa hè, cắm trại & thiên nhiên, vũ trụ,
  nghề nghiệp, lễ hội, học đường & đồ chơi.

**Nhân vật phải đủ bộ phận RIÊNG** (người dùng 2026-10-02, rái cá `OtterToy3dModel` tải từ web Tripo không
texture, mặt lõm trong mũ trùm, tay ôm bóng sát bụng → chỉ chia được đầu 8 múi/thân 4 múi, tô màu vô nghĩa). Tool
chỉ tách được chỗ có **cổ/rãnh thật** hoặc **đổi màu**; khối đắp nổi cùng màu thì không bao giờ tách được. Luật
`char`: đầu, mõm nổi màu nhạt, tai, mảng bụng nổi màu nhạt, tay, bàn chân + đệm chân nổi, đuôi, má — 7–12 bộ phận,
mỗi cái một màu; mũ/áo là lớp vỏ dày có vành; CẤM mũ trùm/mặt nạ ôm quanh mặt, ôm đồ sát bụng, nếp gấp, ngón.
Trên web Tripo phải BẬT texture (không texture = chỉ còn hình để cắt).

**Prompt phải có nhiều DECOR** (người dùng 2026-10-02 "như các model mẫu"). Quét 108 FBX gốc: trung vị **29 mesh
D/model** (tứ phân vị 17–63; 75% gắn trên S). Ảnh tô riêng D (scratchpad `dlook.py`): mặt (mắt, má hồng, mũi,
miệng), đệm chân, hoạ tiết NỔI trên áo/túi/khăn (hoa, sao, lấp lánh, tim, chấm, nút), chuỗi hạt/đinh tán quanh
vành mũ/cổ/vành đế, hoa-sao-sỏi-vỏ sò rải trên mặt đế, emblem tròn trên thành bát. Luật (`prompt.BRIEF` + `decor`
của từng dạng trong `FORMATS`): câu CUỐI prompt bắt đầu bằng `Decor:`, 3–5 nhóm, 15–40 mảnh, mỗi nhóm số lượng +
hình + màu + chỗ; mỗi decor là khối NỔI đơn giản cỡ 1/15–1/25 chiều cao, cách nhau — không vẽ phẳng, không nét mảnh
(sọc, chữ, ria, kẻ caro thành nhiễu). Câu phong cách Tripo đổi "few large parts" → "large simple parts with small
raised decor shapes". Prompt 450–720 ký tự (Tripo cắt ở 1024 tính cả câu phong cách ~225).

**Model lắp ghép nhiều mảnh** (2026-10-05, người dùng: "model Tripo khá đơn giản, muốn đẹp hơn, chi tiết dễ tách"): `BRIEF` bắt mô tả model như đồ chơi LẮP GHÉP từ 12–20 mảnh riêng, gọi tên từng mảnh và cách nó nằm trên mảnh khác (separate, sitting on, wrapped by, raised ring/rim, stacked, groove between); xe: thân chia vỏ trước / chắn bùn / sàn / thân sau / đệm yên / tựa lưng, bánh = lốp + vành + nắp. Câu phong cách Tripo đổi "large simple parts" → "assembled from many separate pieces with visible grooves". Giới hạn CỨNG 720 ký tự; `prompt_cmd` tự nhờ Claude rút gọn nếu > 740 (Tripo cắt 1024 tính cả câu phong cách ~260). Số mặt đề xuất 15.000–20.000 cho model nhiều mảnh.
**Prompt ẢNH cho web Tripo** (2026-10-07, `run.py prompt --mode image`, ô "Ảnh → 3D (web)" — mặc định): người dùng
tạo model trên web bằng Image to 3D (Smart Mesh · P2.0 · Quad · ~11k mặt, 100 credit/lần). Image-to-3D chép đúng
ảnh: mảng một màu lớn = một khối không tách được. Đo 108 FBX gốc (scratchpad `fbx_parts_stats.py`; "bộ phận màu" =
mesh S/M cùng màu chạm nhau): nhân vật trung vị **26 bộ phận (21–29), 9 màu, mảng cùng màu lớn nhất 24%** — vì
LUÔN MẶC ĐỒ (áo có cổ + cổ tay khác màu, quần/yếm, giày, găng, mũ có băng, 1–2 phụ kiện), da chỉ còn ở đầu, tay,
chân. Model Tripo đơn giản (gấu đầu bếp, cáo, thỏ) ra 34–42%, 8–20 bộ phận. `prompt.IMAGE_BRIEF` + `image_rule` /
`image_examples` mỗi dạng trong `FORMATS`, số mẫu lấy từ `sep.TARGET`. Claude trả 4 dòng NAME / PROMPT (≤ 650 ký
tự) / VI / CHECK (điều cần soát trên ảnh); copy nối `IMAGE_TAIL` (toàn thân, 3/4, nền trơn, mỗi bộ phận một màu
phẳng). Nút "Gửi Tripo" từ chối prompt ảnh (gửi vào Text to 3D = phí credit).

**Độ dễ tách sau prep** (`wc/sep.py`, không cần bpy): vùng mặt cùng màu liền nhau trên từng khối, bỏ vùng < 0,5%
diện tích → `prep.json["sep"] = {parts, colors, largest}`, log `[do tach]`. Panel bước 3 so với mẫu cùng "Dạng" ở
bước 1 (`sep.verdict`: mảng > tứ phân vị trên hoặc bộ phận < tứ phân vị dưới → khó tách; thiếu màu chỉ ghi chú vì
bước tô màu bù được); model prep trước đó thì đo một lần từ `prep.npz` (`_sep_measure`, nhớ theo mtime, không ghi
lại prep.json). Hàng đợi ghi "khó tách: mảng 42%, 14 bộ phận" vào cột thông báo.

**Claude chia mảnh đang chọn** (`run.py piece-plan`, nút ở khung "Chia mảnh đang chọn"): khi một part Tripo là khối liền lớn (thân xe 21k mặt) — `cli piece-views` chụp riêng mảnh + context_iso → `planner.piece_plan` (cut/slices/split ở rãnh, 2–6 mảnh) → `_live_split(ob, ops)` cắt ngay, ops ghi vào plan.json, Hoàn tác được. `_live_split` phải `view_layer.update()` trước (matrix_world cũ → mảnh mới lệch vị trí). Bo cong khối lớn: mục tiêu số mặt min(3×, 1,3× + 3000).

### (cũ) hai kiểu
Hai kiểu (ô "Nhân vật chibi / Đồ vật" ở panel):
- `char`: thú chibi làm một việc, 1–3 đồ vật, đế tròn (5 prompt web người dùng đã duyệt).
- `object` (người dùng 2026-10-02 gửi ảnh xe bus mini bo tròn): MỘT đồ vật, 6–12 bộ phận to, bánh/kính/đèn là
  khối nổi riêng, không thanh mảnh. Gửi Tripo với câu phong cách `tripo.STYLES["object"]` ("chunky toy object")
  thay cho "toy figure" (kéo Tripo về nhân vật).
Màu chỉ dùng từ trong `COLOR_WORDS` (khớp bảng màu game). Claude CLI chạy model nhanh (sonnet/low) → ~15 giây.

## 3a prep (`wc/prep.py`)
- Chuẩn hoá: cạnh dài nhất **10**, tâm X/Y = 0, đáy Z = 0, mặt trước nhìn **−Y** (Tripo API nhìn +X → `--turn -90`;
  file tải từ WEB Tripo đã nhìn −Y → `0` — kiểm 2026-10-02 bằng MCP xoay 5 hướng: rái cá, chuột với −90 quay mặt
  sang −X). **Tự tìm mặt trước** (`run.py facing --in X --name N` → `TURN:`; nút ở bước 2, tự chạy khi "Nạp model"
  nếu bật ô "Tự làm khi nạp"): `cli facing` render 4 ô A/B/C/D = xoay 0/+90/180/−90, camera đứng ở −Y, kiểu
  Workbench Solid (xám + cavity + viền; EEVEE với model trắng loá → Claude chọn nhầm lưng) → `planner.facing`
  (sonnet/low, ~20 giây). Đúng cả 3 lần thử (gấu trúc API −90, rái cá + chuột web 0). Đổi góc xoay → `split` tự
  chuẩn bị lại (so `turn` trong prep.json).
- Mỗi **khối rời** của Tripo: **mặc định GIỮ NGUYÊN lưới Tripo** (người dùng 2026-10-01: "model thô đang
  đẹp mà tách xấu" — đừng dựng lại / làm mịn): hàn đỉnh trùng, vá lỗ, tách cạnh dính 3–5 mặt rồi vá lại khe
  → đa tạp kín (cáo: 43/43 mảnh kín, 15k tam giác). Khối vẫn vỡ nặng (> 0,2% cạnh lỗi) hoặc `--remesh` →
  voxel remesh 170 ô/cạnh → bỏ vỏ trong → giảm còn phần ngân sách 19k → Taubin.
- Màu: màu texture thô từng mặt → chuyển sang khối kín (BVH điểm gần nhất) → **làm mịn có giữ cạnh**
  (bilateral, ΔL 14) → gom cụm + chọn slot bảng màu (chép `color.py` của PrimForge, tối đa 14 màu, ưu tiên
  từ màu trong prompt ở `inbox/<Ten>.tripo.json`) → lọc đa số → `clean_labels` (vùng < 0,4% cùng màu sơn
  ΔE < 22 thì nhập; vùng tương phản như mắt giữ).
- **Tách u nhô trước khi cắt** (v3, `_local_height`: độ nhô của đỉnh so với MẶT PHẲNG khớp lân cận bán kính R,
  hai cỡ R = 5% và 8% cỡ model, ngưỡng 0,22 R; cắt rồi dò VÀO TRONG tới tiết diện hẹp nhất = cổ của u; gấu trúc
  của người dùng: 2 bàn tay + đuôi). Bản v2 bên dưới (Laplace) đã bỏ vì cả đầu/thân tròn cũng thành "u". Mõm thấp
  (nhô ngang độ cong đầu) không dò được → luật cho Claude: cắt mõm/má trước khi chia múi. `prep_version` trong
  prep.json: `split` tự chuẩn bị lại nếu cũ (người dùng từng chạy với prep trước khi có tách u).
- (cũ v2) **Tách u nhô trước khi cắt** (`find_bumps` / `split_bumps`, người dùng 2026-10-02: "tai, mắt, đuôi cần được tách
  ra trước khi cắt"; nhát chia múi từng xuyên qua mắt/mũi gấu trúc dính liền đầu): so mặt thật với mặt làm
  phẳng Laplace 80 vòng → vùng cao ≥ 1% cỡ model, ≤ 5% diện tích, ≤ 32% cỡ → cắt ở chân u bằng mặt phẳng khớp
  vòng chân → khối riêng. Chạy cả với model không màu. `--no-bumps` để tắt. Gấu trúc không màu: 2 mắt + mũi + 2 tai.
- **Xe máy đồ chơi tách vụn (2026-10-05)**: hai lỗi của tool, không do người dùng di chuyển model (prep đọc lại file gốc, chỉ dùng góc `wc_turn`). (1) Tìm mặt trước chọn nhầm ô nhìn NGANG (−180 thay vì +90): sonnet/low không ổn định → `facing` dùng model mạnh (task plan) + bắt mô tả từng ô + luật riêng cho XE (đầu xe chính diện, hẹp, một bánh); 3/3 đúng; JSON lồng nhau → `raw_decode`. (2) Tách u nhô chạy trên model đã chia part vì thân xe liền chiếm 43% số mặt (> ngưỡng 35%) → băm đèn pha, moay-ơ, hãm bô thành miếng; nay chỉ tự tách khi part lớn nhất ≥ 70% (model liền một khối), còn lại bật tay ô "Tự tách u nhô" (`--bumps`). PREP_VERSION 10.
- **Dọn part trước khi cắt** (`prep._clean_parts`, PREP_VERSION 8; người dùng 2026-10-02: "khối nào ra khối đó,
  thừa thì xoá, mesh lỗi thì mesh lại"): part cỡ ≥ 4% model nằm khuất ≥ 50% trong part kín khác (moay-ơ/vành lồng
  trong lốp → lộ mẩu vàng hình sao) → BỎ; part hở hoặc có ≥ 4% diện tích "vạt không độ dày" (tia vào trong chạm mặt
  đối diện < 1,5% cỡ: vạt dưới yên 4,6%, part thường < 4%) → `bl.voxel_rebuild` (voxel cỡ/70, vỡ thì cỡ/140; bỏ
  vụn < 1% diện tích; giảm mặt thử nhiều tỉ lệ tới khi còn kín — có lần rơi về bản chưa giảm 30k mặt). Decor nhỏ cắm
  nửa thân (ốc) giữ. Tay: nút "Mesh lại" / "Xoá" / "Ghép" + kiểu chia "Cắt tại con trỏ 3D ⟂ X/Y/Z" (cắt vạt thừa rồi
  xoá), ghi `remesh` / `drop` / `merge` (anchor) vào plan.json.
- **Xoá mảnh li ti** (người dùng 2026-10-05): `plan.execute` xoá mảnh có cạnh dài nhất < `tiny` × cỡ model (mặc định 2,5%, `--tiny`, ô "Xoá mảnh li ti < (% cỡ)" ở bước 3, 0 = giữ hết; nút thùng rác xoá ngay trong cảnh và ghi `"tiny"` vào plan.json). Xe máy part: xoá 46 mảnh (86 → 40), chủ yếu ốc/chấm D.
- **Bỏ part khuất chỉ khi KHÔNG NHÌN THẤY** (`_visible_frac` < 12%, PREP_VERSION 9): luật cũ "khuất ≥ 50%" xoá nhầm 2 quầng mắt + mũi gấu trúc (cắm nửa thân vào đầu, khuất 53% nhưng thấy 46%); moay-ơ trong lốp thấy 5–7%.
- **Tấm mỏng: làm dày rồi mới voxel** (`prep.rebuild`, PREP_VERSION 11, 2026-10-07; dùng chung cho bước chuẩn bị, nút
  "Mesh lại", op `remesh`): áo choàng cáo `CuteFox3dModel` = một lớp vải hở, 75% vạt mỏng → voxel cỡ/70 làm THỦNG 114 lỗ
  xuyên mà vẫn qua kiểm số khối / diện tích → mảnh loang lổ khi tách. Nay đếm lỗ xuyên (`_genus`, > `GENUS_MAX` 6 = hỏng);
  thủng thì `_thicken` (Solidify hai phía 2,4 ô voxel, KHÔNG even offset) → voxel /70 → /140; vẫn thủng thì giữ lưới gốc.
  Cáo: 46,6k mặt, 1 lỗ xuyên, áo dày thêm 0,28. Thử /140 trước: 73k mặt (giảm mặt thì hở → giữ bản đầy đủ) → bỏ. Nút
  Mesh lại trên P08 đã thủng: 114 → 2 lỗ.
- **Model Tripo đã chia part → KHÔNG tách u nhô** (`bumps="auto"`, PREP_VERSION 6): ≥ 15 part ≥ 30 mặt và part lớn
  nhất < 35% số mặt. Xe máy part (83 part, lớn nhất 13%): tách u từng băm đèn pha thành nhiều vòng cung, cắt rời đầu
  ống xả, tạo mẩu lởm chởm trong vành bánh (người dùng: "nhiều phần không có ý nghĩa"). Nhân vật liền khối (gấu trúc
  12 u) vẫn tách. `--no-bumps` = tắt hẳn.
- **Khung mỏng bị mất** (xe máy part 2026-10-02: khung + máy 2454 mặt còn 28 cạnh hở → dựng lại bằng voxel → ống
  mỏng hơn ô voxel biến mất, vỡ 184 mảnh, ra hàng trăm "khối" 2–4 mặt): `_keep_surface` nay bỏ mảnh rác < 4 mặt
  (`_drop_specks`) và bịt lỗ còn sót bằng quạt tam giác về tâm (`_close_loops`, đúng chiều mặt kề); nếu vẫn phải
  voxel mà ra > 3× số mảnh hoặc < 60% diện tích → giữ lưới đã vá (không làm mịn). `PREP_VERSION` 5.
- Ra `work/<Ten>/prep.npz|json|blend` + `plan_front/right/back/left/top.png` (lưới, nhãn số là **toạ độ thật**)
  + `plan_iso.png`.

## 3b/3d Claude (`wc/planner.py`)
Claude CLI `-p`, chỉ được `Read` (ảnh trong `work/<Ten>` và `data/ref`), không sửa file, `WOOLCUT_NO_TRIPO=1`.
Luật cho Claude nằm trong `planner.RULES` (thứ tự cắt, khi nào `cut`/`part`, hệ toạ độ). Ảnh mẫu ở
`data/ref/` (BearArt mỗi mảnh một màu, ảnh trong game, con mực người dùng tự tách). Vòng soát đưa
`parts_sheet.png` + cảnh báo `!!` cho Claude rồi nhận lại toàn bộ kế hoạch mới (hoặc `{"ok": true}`).
**Claude đọc PROMPT của model** (từ 2026-10-02; trước đó chỉ nhìn ảnh, prompt chỉ dùng chọn màu ưu tiên ở prep):
lập kế hoạch, soát và tô màu đều nhận `PROMPT_NOTE` — liệt kê bộ phận prompt gọi tên, bộ phận có trên ảnh phải
thành mảnh riêng, bộ phận Tripo bỏ/gộp thì không bịa nhát cắt (ghi vào `notes`), màu prompt là màu ý đồ.
Nguồn (`prompt.find_prompt`): `work/<Ten>/prompt.txt` (ô "Prompt của model" ở bước 3, `--prompt` của
split/plan/review/paint ghi ra; có file là theo file kể cả rỗng) > `<Ten>.tripo.json` cạnh file model (bước 2
ghi). Model tải từ web Tripo không có tripo.json → bấm nút lấy prompt bước 1 hoặc dán tay.

## 3e tô màu (`planner.paint`, `run.py paint`, nút "Claude tô màu theo bảng")
Claude xem `parts_sheet.png` + ảnh + bảng màu (số slot, màu tên gọi, màu trong game = Highlight Unity ×1,4) rồi
trả `{"colors": {"P01": 15, ...}}` (SỐ SLOT — có hai "Gray": 7 đậm, 25 nhạt). Mỗi mảnh đổi màu thành thao tác
`{"op":"color","target":<tâm mảnh>,"paint":true}` cuối `plan.json` (lần tô sau thay các thao tác `paint` cũ) — nên
cắt lại không mất màu. **Không cắt lại để áp màu** (2026-10-07, người dùng: "có gọi tách đâu mà lại tách"; trước
đây nút chạy lại cả kế hoạch cắt chỉ để có ảnh + áp màu): nút panel (`WC_OT_paint_ai`) ghi các mảnh ĐANG CÓ trong
cảnh ra `parts_paint.blend` → `run.py paint --in` → `cli paint-views` chụp `paint_*.png` + `paint_parts.json` (gồm
cả mảnh tách tay) → `planner.paint(src="paint")` → `paint.json["apply"]` {tên mảnh: material} → panel gán tại chỗ
(`look.apply_piece`, giữ UV), Hoàn tác trả màu cũ + ops plan.json cũ (`UNDO` có `colors` / `plan_ops`). Tô khi tách
(`split --paint`, hàng đợi): `cli paint-apply` gán thẳng vào `parts.blend` + sửa màu trong parts.json + chụp lại ảnh
parts_* (~20 giây, thay cho cắt lại cả model). Luật: múi cùng bộ phận cùng màu, bộ phận chạm nhau tương phản, 8–14 màu.
Model không texture (mèo phù thuỷ) thì tô toàn bộ; có texture thì chỉ sửa màu sai. `split` tự tô khi model
không màu (hoặc `--paint`; ô "Tô màu theo bảng luôn khi tách" ở panel, mặc định bật).

Material: tên đúng bảng + **màu FBX của bảng** (Base Color = `std.PALETTE`, Roughness 0,553) giống hệt model mẫu
(BearArt) — đặt cạnh nhau trong Blender không lệch màu; trong Unity material được khớp theo tên.

Tốc độ Claude CLI (`WOOLCUT_SPEED`, ô "Claude" ở panel): normal = kế hoạch effort medium, tô màu sonnet/low;
fast = sonnet/low cả hai; careful = effort high. Đo 2026-10-02: không cờ thì lập kế hoạch ~13 phút, tô màu ~15 phút; tô màu sonnet/low ~25 giây (cả cắt lại 59 giây). Tô màu nhắm mảnh bằng **điểm neo trên bề mặt mảnh** (`anchor` trong parts.json), không bằng tâm: tâm mũ nón rỗng lọt trong đầu → tô nhầm đầu.
**Model từng chức năng** (2026-10-07, tab **"Cài đặt"** ở hàng nút bước = `wc_step` "SET" → panel `WC_PT_models`, kèm
ô khoá Tripo; cũng có trong Preferences addon `m_<khoá>`, `e_<khoá>`; tên chức năng ngắn vì cột panel hẹp): 9 khoá
`planner.TASKS` (prompt, facing, label, paint, decor, refine, piece, plan, review) → addon ghi `WOOLCUT_MODELS` =
`{khoá: [model, effort]}` ("" = theo chế độ, "default" = model mặc định của CLI = `opus[1m]` trong `~/.claude/settings.json`)
→ `planner.model_for`. Không cài gì = y như cũ. Nút "Dùng gợi ý" = `planner.RECOMMENDED` (Opus/medium cho đặt tên, tô màu,
decor, chia mảnh; Sonnet/low viết prompt) — vì Sonnet/low đặt tên sai ~30/73 mảnh (gấu xe máy 2), tô màu ra cầu vồng (chim).
`refine_piece` gọi với `force` (nút "Claude chia mảnh đang chọn") = khoá `piece`, còn lại = `refine`. Alias CLI `haiku`,
`fable` đã thử chạy được. Ô "Claude" (Nhanh/Vừa/Kỹ) cũ bị gỡ khỏi panel bước 3 → nay nằm trong khung Model Claude.

## 3c cut (`wc/tm.py` lõi hình học, `wc/plan.py` thực thi)
- `TM`: lưới tam giác numpy + `col` (chỉ số màu; `-2-c` = mặt nằm dưới miếng dán D, nhớ màu gốc c) + `cap`
  (mã nhát cắt nếu là mặt nắp).
- **Nhát cắt**: giao tuyến mặt phẳng → các vòng kín → chọn vòng → chia tam giác dọc vòng, nhân đôi đỉnh →
  nắp phẳng bằng **một** CDT 2D dùng chung hai bên (hai mảnh khít tuyệt đối). Trong/ngoài của tam giác CDT
  xác định bằng **loang theo topo** (qua cạnh ràng buộc thì đổi chẵn/lẻ), không bằng tâm tam giác.
- Mặt phẳng tự xê vài % cạnh lưới để điểm giao không sát đỉnh (≥ 3% cạnh) — không thì CDT gộp đỉnh, nắp hở.
- `local`: vòng quanh điểm; không tách rời được (quai túi nối đuôi với thân) thì thêm dần vòng gần nhất.
  Mảnh ra bị hở thì xê mặt phẳng thử lại, không được thì bỏ nhát cắt (giữ mảnh kín 100%).
- `snap`: dò ±snap và nghiêng ≤ 20° tìm **chỗ thắt thật** = cực tiểu TRONG của tiết diện (hai bên đều to hơn
  ≥ 12%); vùng phải chứa điểm đích và ≥ 35% tiết diện ban đầu (không thì nhảy sang góc túi/quai — đuôi cáo).
  Không thấy thì nới khoảng tìm ×2, ×3, ×4; vẫn không có thì GIỮ mặt phẳng Claude chỉ (`fallback="keep"`). Cách cũ
  (tiết diện nhỏ nhất) trôi ra CHÓP vì tai/tay/đuôi thon dần (gấu đầu bếp 2026-10-02: tai chỉ lấy chóp; cổ z 6,0
  trong khi rãnh cằm ở 5,0 → cằm dính thân). Nghiêng 40° đã thử: tay phải ăn sang nửa mặt → giữ 20°.
- `cut` nhắm vào U NHÔ (tai, sừng, đuôi): `Run._bump_plane` — có vùng u (`prep.find_bumps`, R 0,8) cách `at` < 0,8
  và mọc lệch hướng Claude < 50° → cắt ở CHÂN u theo hướng mọc thật (PCA vùng u), như `prep.split_bumps`; mảnh cắt
  ra to quá 3,5 R thì bỏ, quay về mặt phẳng Claude. Mặt phẳng Claude gần thẳng đứng lấy cả mảng bầu dục sườn đầu.
- `prep.split_bumps` chỉ chạy trên khối KÍN; khối "thân" Tripo hay gồm nhiều mảnh rời (tạp dề, cán bột) có mảnh hở
  → bỏ qua cả thân (gấu đầu bếp). Ép chạy thì băm tay cầm bánh gừng thành 5 cục → không bật; tai do `_bump_plane`
  lo. Kiểm loại mảnh cắt ra chỉ xét mảnh có NẮP của nhát đó (trước xét cả mảnh rời khác → huỷ nhát tai).
- `part`: vùng màu quanh điểm → mặt phẳng PCA của biên màu (bỏ mép nắp cũ) → tinh chỉnh ít sai màu nhất;
  sai màu > 25% thì **không cắt** (biên màu nằm trên mặt cong: mũ, túi → dùng `cut` mặt phẳng tự chọn).
- Mảng màu PHẲNG tương phản (độ cao/đường kính ≤ 0,12) tới 3% diện tích (quầng mắt gấu trúc) cũng tách trước;
  mảng to thì luật cỡ tự chọn S/D.
- Trước mọi nhát cắt: chi tiết nhỏ tương phản (≤ 0,6% diện tích, ΔE danh nghĩa ≥ 22: mắt, mũi, lòng tai)
  → **miếng dán D** (vỏ mỏng 0,05), mặt bên dưới giữ màu gốc. Sau cắt: vùng ≤ 1,2% không chạm nắp → D;
  vùng chạm nắp là phần dư của bộ phận kế bên → tô theo mảnh.
- Cuối: màu mảnh = màu chiếm diện tích lớn nhất (bỏ nắp, bỏ mặt dưới D); cân số S/M về [min, max];
  loại S/M/D (`std.auto_kinds` theo cỡ **model**); D gắn `wc_host`; cảnh báo mảnh vụn / lẫn màu.
- Ra `parts.blend` (P01…, `wc_kind_auto`, `wc_color`, `wc_host`), `parts.json`, ảnh `parts_front/iso`,
  `parts_ids_*`, `parts_explode_iso`, **`parts_sheet.png`** (mỗi mảnh một ô: tên loại màu).

## Các kiểu chia (plan op) — kiểm 2026-10-02 trên khối cầu: mọi kiểu kín 100%, tổng thể tích khớp tuyệt đối
| op | kiểu | số mảnh |
|---|---|---|
| `split` axes x/y/z | đôi trái-phải / trước-sau / trên-dưới, 4 múi, 8 múi (BearArt) | 2, 4, 8 |
| `slices` n hoặc `at` | lát/tầng song song (đều hoặc vị trí tuỳ ý) | n |
| `sectors` n, `axis`, `layers` | múi cam quanh trục bất kỳ; n lẻ = cắt 2n nêm rồi ghép cặp (cắt từng múi riêng thì mặt phẳng tự xê lệch → thừa/thiếu 1–4%); × tầng | n, n×m |
| `grid` [nx,ny,nz] | lưới ô vuông | nx·ny·nz |
**Khối dài nằm nghiêng** (ống kính, chân máy, tay giơ chéo): `tm.piece_frame` — PCA bề mặt; độ dài/độ dày ≥ 1,4
và trục dài lệch trục thế giới gần nhất ≥ 12° → xoay hệ trục (Rodrigues, xoay nhỏ nhất) để trục thế giới đó trùng
trục khối; mọi kiểu chia (`split`, `slices`, `sectors`, `grid`) và xem trước ở panel dùng chung R. Khối tròn / đứng
thẳng → I (đầu 8 múi BearArt không đổi). `"axis": "long"|"mid"|"short"` = trục riêng; `"world": true` = tắt xoay.
Lỗi gốc (người dùng 2026-10-02, chuột ngắm sao, chế độ Nhanh): `split x,y` "nón tròn" có target rơi vào ống kính
→ ống nghiêng bị 4 mặt phẳng đứng cắt thành nêm chéo hình X. Thử ống nghiêng 35°: lát vuông góc trục 0°, kín 100%.
Mảnh vụn < 1% thể tích sinh ra khi chia được nhập vào mảnh gần nhất.

**Thứ tự & "không ép cắt"** (người dùng 2026-10-02): tách rời bộ phận riêng (tay, chân, ống bô, đũa, thìa…) trước,
rồi CHỈ chia múi khối to. Code ép: `split/slices/sectors/grid` bỏ qua khối < 3% thể tích model (`SPLIT_MIN_VOL`,
`"force": true` để ép). `balance` KHÔNG ép cắt / gộp nữa: thiếu S/M chỉ bổ đôi khối ≥ 8% thể tích, thừa thì giữ
nguyên (trước gộp mảnh nhỏ vào mảnh kề = mất part riêng của Tripo).
**Model Tripo "có part"**: GLB tải từ web có thể là MỘT mesh liền (xe máy đầu: 65 mảnh rời, thân 11k mặt gồm khung,
bình, yên, phuộc, bánh trước) hoặc nhiều part rời (`… (1).glb`: 196 khối, lớn nhất 2,5k mặt). Mỗi mảnh rời = một
mảnh sẵn (`Run.__init__` tách thành phần liên thông); Claude chỉ chia các part to.
**Bo cong mép cắt** (`bl.round_seams`, `--bevel` / ô "Bo cong mép cắt", mặc định 0,075 — người dùng thấy 0,15 "cong quá", chỉ M/S): LĂN MÉP — đỉnh bề
mặt thật cách mép s < w kéo vào trong theo cung tròn, đỉnh mép trượt trong mặt phẳng cắt; hai mảnh kề thành rãnh tròn
như model mẫu. Nhân theo độ sắc góc (|N·C| ≥ 0,75 = cắt lướt → không bo), kẹp 35% độ dày đo bằng tia (vỏ mỏng), bỏ
đỉnh pháp tuyến triệt tiêu. `bmesh.ops.bevel` đã thử: tự kẹp theo cạnh lưới ~0,05 → 0,12 hay 0,25 như nhau. Cắt
lướt không có hệ số góc → gai dưới chân kính chắn gió. Mặt nắp mang thuộc tính `wc_cap` (mã nhát cắt).
**Bo cong = VOXEL + LÀM TRÒN** (mặc định 0,15 — 0,3 rãnh rộng, "các mesh cách hơi xa"; đỉnh xa mép ép về đúng bề mặt gốc bằng smoothstep trong dải 1,6 w — bản đầu voxel cả mảnh nhìn mềm nhũn) (`fillet.fillet`, mặc định từ 2026-10-05 tối; `fillet_geo` cũ hay thất bại ở vỏ mỏng / chỗ hẹp → còn nếp gấp, mép vuông): dựng lại mảnh bằng voxel (ô = max(w/3, cỡ/140) ≤ cạnh ngắn/8) → Laplace có trọng số (giảm dần theo khoảng cách tới mặt cắt cũ, trong 1,6 w; ≈1,2·(w/ô)² vòng) → giảm mặt về ~3× số mặt gốc (giữ kín). Mọi mép cắt + nếp gấp thành rãnh tròn, không trường hợp hỏng; đĩa 6 múi 4–15 s, ~1.300 mặt/múi. Không còn mặt nắp (không cạnh sắc).
**Cắt đều**: `sectors` MỌI n ≥ 3 dùng Boolean chính xác (khối tự giao → `_rebuild` rồi thử lại; chẵn mà vẫn hỏng → k/2 mặt phẳng qua trục); `plane_cut` khi kẹt xê mặt phẳng 0,04% → 0,15% → 0,5% cỡ trước (cũ 1,3% ngay → các nửa lệch nhau, múi không gặp ở tâm).
**Bo cong = HÌNH HỌC MỚI** (`wc/fillet.py`, thay `bl.round_seams`, mặc định 0,25 (0,1 chỉ ra đường kẻ mảnh, chưa thấy tách mảnh); người dùng 2026-10-05 "có thể cắt bớt và tạo thêm mesh"): mỗi mặt cắt → chia nhỏ cạnh mặt thật dài > 2,5 w trong dải 1,6 w (tam giác mảnh sát mép làm plane_cut từ chối) → cắt bỏ lớp mỏng sâu w (`plane_cut` local, `shift_rel` nhỏ) → dải cong ¼ elip 4 bậc từ vòng mép (r ≤ w, kẹp theo bề rộng nắp tại chỗ) → nắp mới thu nhỏ (`tessellate_polygon`, có lỗ). Bước nào hỏng thì giữ mép vuông cho nắp đó (log `bo cong nap … bo qua`). Đĩa xiên nướng 3 múi: ~700 → ~5.300 mặt/múi; xe máy 17 mảnh bo, cắt 45 s. Dùng cả khi cắt toàn bộ và nút Chia.
(cũ) **Bo cong mượt** (2026-10-05, mặc định 0,06, thuộc tính panel `wc_bevel2`): `bl.round_seams` = (1) chia nhỏ cạnh BỀ MẶT THẬT trong dải 2,5 w quanh mép tới ≤ w/2 (không chia mặt nắp; mảnh ~700 → ~2400 mặt), (2) lăn mép (`_roll_seams`), (3) làm mịn Laplace dải 1,5 w chỉ theo hàng xóm mặt thật (nắp CDT/Boolean là tam giác dài → kéo mép vào giữa thành khe thủng). Lăn trực tiếp trên lưới Tripo thưa làm mặt gãy mảng (đĩa xiên nướng). 0,1 trên đĩa mỏng bắt đầu vảy.
**Múi lẻ** (`sectors` n lẻ): Boolean EXACT giao với từng lăng trụ nêm (`_boolean_sectors`), nắp gán mã theo đường biên góc; cách cũ 2n nêm rồi ghép hỏng vì mặt phẳng tự xê lệch khác nhau hai bên → ghép thất bại, giữ cả mặt cắt giữa (đĩa chia 3 ra 6 rãnh). `merge` nay chỉ bỏ MẶT TIẾP GIÁP (mã có diện tích hai bên khớp nhất).
**Khối tự giao** (vành/moay-ơ lồng trong lốp — bánh trước 145–161 cặp mặt cắt nhau): mọi mặt phẳng qua đó hỏng →
`Run._rebuild` dựng lại RIÊNG khối đó bằng voxel (cỡ/110), giảm về ~1,3× số mặt, màu/nắp theo mặt gần nhất, rồi
cắt lại. **Vòng suy biến** (gai 10 mặt cạnh ống phuộc, tiết diện 0,0007) làm CDT hỏng cả nhát → `plane_cut` thử lại
sau khi bỏ vòng < 2e-5·size². Panel "Chia mảnh đang chọn" ghi op có
`anchor` (điểm trên bề mặt mảnh) + `manual` vào `plan.json` rồi cắt lại; "Bỏ lần chia" xoá op manual cuối.

## 4 export (`wc/export.py`, `wc/uv.py`)
**Mảnh D = Deco như bộ gốc** (người dùng 2026-10-02): quét 108 file: 81% D dùng `Deco_mat*`, 85% trong đó UV dồn
vào MỘT điểm trên `Deco_Texture.png` (512×256, 4 hàng × ~32 cột dải màu). `data/deco_points.json` = 368 điểm bộ
gốc đã dùng + màu sRGB tại điểm (dựng bằng scratchpad `decoscan.py` + `decopoints.py`). Xuất: D → material
`Deco_mat` (Unity chỉ có `Game/Material/Deco_mat.mat`) + mọi UV = điểm có màu gần màu bảng của mảnh nhất
(CIEDE2000 − 2·log10(số lần dùng)); M/S giữ material bảng màu. Cáo: lòng tai hồng → (0,08; 0,21), mắt đen →
(0,99; 0,76), ΔE 1,8–7. `.map.json` ghi `deco_uv`.

Loại: `wc_kind` (chọn tay) > `wc_kind_auto`; màu: material đầu tiên (người dùng đổi) > `wc_color`.
Cây chuẩn bộ gốc (root xoay X 90 scale 0.01, nhóm S_/M_, D_ là con của mảnh nó trang trí), FBX 7400 + `.meta`
(giống hệt meta gốc trừ guid → trong Unity cỡ do nội dung FBX quyết định) + `.map.json`.
- **Cỡ**: `--size` / ô "Cỡ" ở panel, mặc định **8,2 = BearArt** (người dùng 2026-10-02: file gốc kéo vào to hơn;
  bộ gốc 4,3–8,2, trung vị 6,1). Game không tự co model theo khung.
- **UV kiểu bộ gốc** (`uv.unwrap`): đo bộ gốc = 1–3 đảo UV/mesh, 2,148 ô/m, vân len chạy dọc chiều dài bộ phận.
  Seam = cạnh sắc (mép nắp) → nắp phẳng là một đảo; mặt cong rạch thêm đường ngắn nhất (ưu tiên phía sau +Y)
  cho thành đĩa → `uv.unwrap` Minimum Stretch → từng đảo co giãn về 2,148 ô/m rồi **căn theo khung thế giới**
  (`_fit_islands`, người dùng 2026-10-02: "mảnh này và mảnh kia không có tí liên kết"): xoay cho Z thế giới chạy
  theo +V (đảo nằm ngang thì Y), dịch cho v ≈ z·mật độ, u ≈ hướng ngang·mật độ → hai múi cắt từ một khối cùng
  hướng vân và hàng mũi gần khớp ở đường nối (soi bằng scratchpad `stripes.py`: sọc liền qua múi đầu/thân/đế
  gấu trúc). Chiếu hộp cũ ra ~15 đảo/mảnh, vân đứt ở mọi góc → đã bỏ (chỉ còn dự phòng).
- **UV2 `uvSet` cho hiệu ứng tan dần** (`uv.flow_uv`, chỉ M/S): shader `UserWooler` `clip(uv2.y − _Progress −
  noise(positionOS.xz))`; `WoolUv2Validator` đòi uv2.y trải ≥ 0,5 của [0,1]. Đo BearArt: kênh thứ hai tên
  `uvSet`, chiếu PHẲNG, y = 0 ở đỉnh → 1 ở đáy (mảnh dẹt nằm ngang: theo chiều dài), x cùng tỉ lệ. Mỗi mảnh tự
  trải đủ 0..1.
- **Tâm mảnh ở GIỮA mảnh** (tâm hộp bao, người dùng 2026-10-02) — khác BearArt (mọi tâm ở gốc model). `--pivot
  origin` / bỏ ô "Tâm mỗi mảnh ở giữa mảnh" để về kiểu BearArt. D là con của mảnh chủ: `matrix_basis` = tâm D −
  tâm chủ. Cắt (`plan.execute`) và chia tay (`_live_split`) cũng đặt tâm giữa mảnh (`uv.center_origin`).
  `primforge check` báo "transform con = identity" khi tâm ở giữa — đúng ý, bỏ qua.
- Ghép cặp tam giác thành tứ giác (`to_quads`, giữ cạnh sắc).
Chấm bằng `python primforge/run.py check --fbx woolcut/out/<Ten>.fbx` (chỉ đọc): cáo, gấu mèo, mèo phù thuỷ
2026-10-02 đều CAN SUA 0, UV 2,15 ô/m, 1–2 đảo/mảnh.

## Panel
- 2026-10-07 người dùng bỏ nút "Làm lại từ đầu (dựng khối lại)" ở cuối bước 3 — prep tự dựng lại khi đổi model
  hoặc tăng `PREP_VERSION`; `parts_only.reprep` vẫn còn cho code khác gọi.
- Bước 3 có 3 cách tách (người dùng 2026-10-02):
  * **"Tách theo part (không cắt)"** (`split --parts-only`): mỗi part / khối rời Tripo = một mảnh, kế hoạch rỗng
    (cũ → `plan_prev.json`), không gọi Claude cắt; xe máy part 104 mảnh, 28 s. Sau đó tự chia ("Chia mảnh đang chọn")
    / ghép ("Ghép mảnh đã chọn" — ghi `{"op":"merge","anchors":[...]}` vào plan.json để Cắt lại không mất).
  * **"Claude lập kế hoạch (xem trước)"** (`split --plan-only`): Claude viết plan.json, CHƯA cắt; tiến trình nền chạy
    thử (`cli trace` → `plan.dry_run` → `plan_trace.npz`: mảnh THẬT + mặt phẳng THẬT của từng nhát, kể cả nhát nhắm
    vào mảnh do nhát trước cắt ra, sau dò chỗ thắt / theo u nổi). Panel: danh sách nhát (`WC_UL_plan`: tick bật/tắt,
    đổi số múi), bấm nhát nào viewport vẽ mảnh đó (vàng) + mặt cắt (đỏ) (`_draw_plan`); các part hiện mỗi part một
    màu (collection "WC 3 · Khoi" từ prep.blend). "▶" chạy thử lại sau khi đổi; "Xác nhận tách" ghi `skip`/`n` vào
    plan.json rồi `split --keep-plan --rounds 0`. `plan.execute` bỏ qua op có `"skip": true`.
  * "Tách tự động" như cũ (lập kế hoạch + cắt + soát + tô).
- **Luồng chính (người dùng 2026-10-05)**: "Tách bộ phận + đặt tên (không cắt)" = `split --parts-only` → sau cắt `planner.label` (Claude sonnet/low đọc parts_sheet/parts_ids_all → `labels.json` [{name, anchor, label}], tên tiếng Việt có dấu) → addon `apply_labels` đổi tên object "P05 tai trái" theo điểm neo gần nhất (sửa `wc_host`). Người dùng tự chọn bộ phận để chia; kiểu mặc định **AUTO** (`_auto_split`): dài (≥1,8× bề rộng) → 2–3 khúc theo trục dài; dẹt → đôi; tròn → 4 múi. Khung kế hoạch xem trước của Claude đã ẩn (code còn).
- **Hoàn tác tức thì**: chia / ghép / xoá / mesh lại KHÔNG xoá mesh cũ mà cất vào collection ẩn "WC 3 · Goc (an)" (`_archive`), ngăn xếp `UNDO` (≤ 30) ghi tên cũ / mới + số op plan.json trước đó; nút "Hoàn tác (n)" trả lại ngay và cắt plan.json về như cũ (`_undo_last`). `load_parts` xoá ngăn xếp. Không còn ngăn xếp thì quay về cách cũ (bỏ op manual cuối + cắt lại).
- Chọn file model ở bước 2 là nạp ngay (`wc_autoload`, timer 0,05 s vì không gọi operator trong callback thuộc tính).
- **Tự chạy hết** (ô ở bước 2, `wc_autochain`, 2026-10-05): chọn file / Nạp model → `chain_start` → tìm mặt trước → `parts_only` (tách + đặt tên + tô màu nếu bật) → `decor_ai`. Trạng thái `CHAIN["stage"]`, mỗi bước gọi bước sau trong done-callback qua timer (đợi `running()` hết); nút Dừng huỷ chuỗi. Timer không chạy ở Blender -b → test bằng giả lập (scratchpad `t_chain.py`).
- **Chia mảnh có yêu cầu** (`wc_piece_hint`, `--hint`): Claude làm đúng yêu cầu; op mới `carve` (Boolean EXACT với khối bao ring / cylinder / box / sphere: giao = mảnh mới, hiệu = phần còn lại, mặt mới gán mã cắt chung) cho bộ phận ôm quanh khối khác (vành mũ, cổ áo) — luật bắt dùng ring thay mặt phẳng.
- **Xoay mặt cắt tay** (2026-10-06): khung "Chia mảnh đang chọn" có X / Y / Z (độ, quanh trục thế giới, `wc_split_rot`) + nút "Trục thế giới" (`wc_split_world`: bỏ tự nghiêng theo khối dài) + đặt lại. Op ghi `rot` / `rot_world`; `plan._frame` = Ru @ piece_frame; kiểu "Cắt tại con trỏ" xoay thẳng pháp tuyến. Xem trước đỏ xoay theo. Thử khối cầu: 30° quanh Z → pháp tuyến (0,866; 0,5; 0).
- **Góc LẬT (tilt, quanh X)** (2026-10-06): tìm mặt trước chụp 6 ô — A–D xoay quanh Z, E = lật cho ĐỈNH ra trước (+90), F = lật cho ĐÁY ra trước (−90), chỉ chọn E/F khi model nằm ngửa/úp. `run.py facing` in `TURN:` + `TILT:`; `load.load(path, turn, tilt)` = Rz(turn) @ Rx(tilt); prep.json lưu `tilt`, đổi lật → chuẩn bị lại; panel bước 2 có "Lật ↑ / Lật ↓" (`wc_tilt`), mọi lệnh split/parts truyền `--tilt`.
- Hàng nút **1 Prompt · 2 Model · 3 Tách · 4 Xuất · Tất cả** (`wc_step`, người dùng 2026-10-02): bấm bước nào chỉ hiện
  khung bước đó (`poll` của `WC_PT_1..4`), khung Nhật ký luôn hiện. Mặc định "Tất cả".
- Hai ô việc nền độc lập: `main` (tách, cắt, gen, xuất) và `prompt` — đang tách vẫn bấm "Claude viết prompt" được
  (người dùng 2026-10-02). Prompt không đổi ô Tên (tên prompt lưu `wc_prompt_name`, chỉ dùng khi gửi Tripo).
  Nút "Copy prompt (dán lên web Tripo)" chép prompt + câu phong cách (`full_prompt`).
- "Chia mảnh đang chọn": cắt NGAY trong Blender bằng lõi `wc.plan.Run` (`_live_split`), mảnh mới được trải UV +
  vật liệu (`look.apply_piece`), op (có `anchor`) ghi vào `plan.json`. Xem trước: draw handler GPU vẽ mặt phẳng
  cắt (đỏ trong) + viền mảnh đang chọn (vàng) theo kiểu/số phần đang chọn (`_draw_preview`).
- Vật liệu khi xem (`wc/look.py`): M/S = tên bảng màu, Base Color = len đan `knit_basecolor.png` × màu game
  (Unity H × 1,4), UV `map1`; D = `Deco_mat` + UV một điểm. Solid: `obj.color` + Color = Object (D dùng chung
  Deco_mat nên không dùng Color = Material). Nút "Xem như trong game" = Material Preview. Xuất thì M/S về material
  phẳng màu FBX (`palette_material(game=False)`) giống model mẫu.
- Đổi màu mảnh D = đổi ô màu Deco; đổi loại D ↔ M/S = đổi vật liệu + UV.
- Đang chạy việc nền: mọi nút bị khoá (`_Locked.poll`), các khung chỉ hiện "Đang chạy…"; còn nút Dừng.
- Tên model **tự lấy từ tên file** khi chọn/nạp model (`model_name`). Trước đây tên giữ nguyên → người dùng tách
  mèo phù thuỷ dưới tên FoxMailCarrier, ghi đè thư mục con cáo (2026-10-02).
- Model không màu (Tripo xuất "parts" không texture): ảnh kế hoạch tô mỗi khối rời một màu pastel, Claude được
  báo không dùng `part`/`decal`; panel cảnh báo "chỉ tách theo hình".

## Thời gian chạy (đo 2026-10-02, xe máy part 197 mảnh)
Một lượt "Tách" = prep (~15 s) + Claude lập kế hoạch (Vừa: vài phút; Nhanh: 1–2 phút) + cắt + Claude soát (~1 phút,
có sửa thì cắt lại) + Claude tô màu (~30–60 s) + cắt lại. Bước cắt từng mất 151 s, trong đó `render.sheet` 119 s
(EEVEE render từng ô + render RIÊNG từng nhãn chữ ≈ 400 lần render) → nay ô bằng Workbench, nhãn một lần render
(`_text_strips`): cắt 44 s (hình học < 3 s, 8 góc ảnh 14 s, bảng mảnh 17 s, UV 8 s). Đo bằng scratchpad `prof_cut.py`.

## Decor (2026-10-05) — `wc/decor.py`, `planner.decor`, panel bước 3 khung "Decor"
- **Thư viện** `data/decor/` (`run.py decor-lib` dựng lại): `library.blend` = 27 decor của người dùng
  (`D:\BlenderTool\Deco\DeCo.fbx`, `D_Oai_1..27`, cùng Deco_Texture với game) + 15 khối đơn giản tự dựng (mắt tròn /
  bầu dục / nhắm, chấm sáng, má hồng, mũi tròn / tam giác, miệng cười / mèo / há, ria, lông mày, chấm, nút, đĩa).
  Chuẩn hoá: tâm hộp bao ở gốc, cạnh dài 1, MẶT TRƯỚC −Y, đầu +Z. `catalog.json`: id, tên vi, mô tả en, nhóm, `mode`
  "multi" (giữ UV nhiều ô màu Deco) / "tint" (UV dồn một điểm, đổi màu được), dims. `thumbs/` icon + `catalog.png`
  (bảng tổng Claude xem). DeCo `D_Oai_15` UV 11,9 → đưa về [0,1].
- **Claude gắn** (`run.py decor --name X --in parts_decor.blend --allow id,id`): `cli decor-views` chụp ảnh lưới
  các mảnh HIỆN TẠI + `decor_parts.json` → Claude (sonnet/low) chọn decor TRONG SỐ ĐƯỢC TICK, không cần dùng hết; đã có
  mắt thì không gắn mắt; trả `{decor, host, at, view, size, rot, color}` → `decor_plan.json`. Thiếu decor đơn giản thì
  Claude TẠO (`new_decor`: ghép sphere/box/cylinder/cone/torus/star/arc, ≤ 3 cái, id `ai_*`) → `cli decor-custom` dựng
  `custom.blend` + icon, panel báo "Claude tạo decor mới: …" và tự tick.
- **Đặt** (`place_decor_plan`, trong addon): `view_layer.update()` trước (matrix_world cũ → lệch); tia bắn vào HỢP
  mọi mảnh M/S (`decor.union_bvh`) bắt đầu 1,2 đơn vị trước điểm Claude chỉ (bắn từ xa thì "top" trúng đỉnh đầu) → bề
  mặt nhìn thấy đầu tiên; mảnh chủ = mảnh tia chạm (tên Claude đưa chỉ là gợi ý — không có tên bộ phận Claude từng chọn
  lát mỏng trong thân, nút lọt vào trong). Pháp tuyến trung bình lân cận, mặt trước decor theo pháp tuyến, lún 45% độ
  dày; cỡ kẹp [0,25; 2] (eye_shine ≥ 0,12). Object `Dc## <tên>`, `wc_kind` D, `wc_host`, `wc_decor`, `wc_decor_uid`,
  `wc_decor_multi`.
- **Lưu** `work/<Ten>/decor.json` (uid, decor, màu, ma trận, host) → `load_parts` (Cắt lại) đặt lại. Xoá decor = bỏ
  khỏi decor.json (không ghi op drop vào plan); "Xoá hết decor"; Hoàn tác đồng bộ decor.json. "Xoá mảnh li ti" bỏ qua decor.
- **Xuất**: D có `wc_decor_multi` giữ UV `map1` + `Deco_mat` (không dồn điểm). Thử gấu đầu bếp: 16 decor, bánh quy
  696 mặt UV trải 0,7 × 0,5, cha là mảnh M.

## Tách sâu (2026-10-06) — `wc/crease.py`, `wc/refine.py`, `planner.refine_all`, nút "Claude tách sâu"
Người dùng: "tách các model có ý nghĩa ra thì tiếp tục facing và detect xem nên tách gì nữa cho từng part; mesh có nếp
gấp thì tách part cho các phần đó nếu có ý nghĩa riêng". Tripo hay gộp nhiều bộ phận một khối (gấu đi xe: đầu + mũ + tai
+ tay + chân + thân = 1 mảnh 2740 mặt; thân xe + yên + sàn = 1 mảnh).
- **Nếp** (`crease.edge_bend`): góc lõm TỪNG CẠNH (hai mặt kề, dấu theo (n2−n1)·(c2−c1) < 0), KHÔNG làm mịn pháp tuyến —
  rãnh hẹp (vành mũ, gấu áo) = đáy lõm + hai mép lồi, làm mịn thì triệt tiêu (lần thử đầu chỉ bắt được cổ). Cạnh
  ≥ 0,30 rad = nếp; gom thành dải, chia đôi (2-means) tới khi mỗi dải nằm gọn một mặt phẳng.
- **Ứng viên** (`crease.candidates`, ≤ 20, khối lớn trước): mỗi dải → (a) mặt phẳng khớp nếp (3 hướng thử: chứa nếp +
  phân giác hai mặt / chỉ theo điểm / vuông góc phân giác — cái cuối cho TAI: nếp chạy vòng chân tai, hai cách đầu ra
  mặt dọc xẻ đôi đầu), chọn hướng có vòng cắt chạy SONG SONG theo nếp nhiều nhất (`_Hot.coverage`, cạnh nếp |cos| ≥ 0,55
  — tính cả nếp cắt ngang thì lát xiên qua đầu cũng "đạt"); (b) **khép nếp hở** (`closure_mask`): nếp chỉ chạy một
  phía gốc tay → nối hai đầu bằng Dijkstra vòng qua PHÍA KIA (cấm đỉnh sát nếp) → vòng kín → miền nhỏ = phần tách. Tay
  gấu áp sát bụng chỉ ra bằng cách này.
- **Cắt theo nếp thật, không phẳng** (`refine_plane`, `harmonic`): bề mặt = mạng điện trở, dẫn qua cạnh =
  ℓ/d·exp(−(β/0,22)²); đầu phần tách (xa mặt phẳng ≥ 50%) = 1, phần còn lại ngoài dải ±6% quanh vòng = 0, giải Laplace
  (CG + Jacobi, `np.bincount`) → miền > 0,5 nằm đúng trên nếp, chỗ nếp đứt nối tròn. Hạt giống chỉ ở ĐẦU phần tách:
  đặt ở cả hai đầu một chuỗi hai nếp (cổ tay + vai) thì đường 0,5 rơi giữa cẳng tay. `split_by_mask`: biên theo cạnh
  lưới, làm mịn Taubin trượt trên bề mặt gốc (BVH), bịt nắp CDT trên mặt phẳng khớp (tự cắt → quạt từ tâm), nắp chung
  hai bên mang mã cắt → fillet bo cong như mọi nhát khác. Lọc: biên phần tách ≥ 45% trên cạnh nếp (`_cover`), phẳng
  thì ≥ 70%; 0,4% ≤ phần tách ≤ 62%. Trùng (cùng tâm + thể tích, hoặc IoU ≥ 0,8) bỏ.
- **Op `crease`** (`plan.op_crease` → `crease.apply`): ứng viên ghi `part`/`rest` = tâm các mặt SÁT biên hai phía,
  `seed_r: 0` (mặt gần nhất) → tái hiện ĐÚNG nhát Claude đã xem (đã thử: thể tích phát lại khớp 100%); Claude tự chỉ thì
  vài điểm, `seed_r` 0,035. `anchor` = điểm ngay tại nếp → mảnh đích = mảnh có bề mặt gần nhất. Phẳng: `at`/`normal`/`planar`.
- **Luồng**: `run.py refine --name X --in refine_in.blend --pieces "a|b" [--hint] [--force]` → `cli refine-views`
  (Workbench: `refine/<mảnh>/context.png`, `piece_*.png` lưới toạ độ, `cands.png` = 2 ô bản đồ nếp đỏ + ô #k phần
  rời ra tô đỏ, `cands.json`) → Claude SONG SONG (4 luồng) mỗi mảnh: `split` / `pick` [{cand, label}] / `ops` thêm
  (crease theo điểm, carve, cut) / `rest` → `refine/refine_plan.json` (pick xếp nhỏ trước: tai rồi mới đầu).
  Addon `start_refine`: cắt ngay (`_live_split` + nhãn → `_name_pieces` ghép điểm `tip` với mảnh gần nhất, mảnh lớn
  còn lại = `rest`), op vào plan.json, `labels.json` ghi lại từ cảnh (`_save_labels`), mảnh "không tách" đánh dấu
  `wc_refined`. Vòng 2 (`wc_refine_rounds`, mặc định 2) xem tiếp mảnh MỚI còn ≥ `wc_refine_min` % thể tích.
- **Chống hỏng khi cắt nhiều nhát nối tiếp** (gấu 2026-10-06):
  * `_clean_mask` trước mọi `split_by_mask`: đỉnh THẮT EO (biên chạm chính nó → không bịt nắp; cắt đầu SAU khi đã cắt
    tay / má) → mặt quanh đỉnh theo đa số, KỂ CẢ mặt hạt giống (vành hạt giống nằm ngay trên biên); miền bị bao kín
    không chứa hạt giống của phe mình → đổi phe.
  * `_merge_tiny`: mảnh vụn < 0,3% / < 30 mặt sau nhát cắt → nhập mảnh lớn gần nhất.
  * `fillet()` bỏ thành phần rời 2–12 mặt thể tích 0 sinh ở mép cắt; `_live_split` bỏ vụn cũ còn sót (không thì vòng 2
    tách "thân" ra 9 mảnh, 7 mảnh rỗng).
  * Planner: bỏ ô chồng lấn MỘT PHẦN với ô đã chọn (`_drop_overlaps`, mẫu điểm `part_s`/`rest_s` trong cands.json; lồng
    nhau như tai trong đầu thì giữ); op `crease` Claude tự chỉ điểm mà rơi gọn trong một ứng viên → dùng ứng viên đó
    (`_snap_cand`; Claude chỉ điểm "chân trái" → Laplace lấy cả hai chân).
  * Đặt tên: mỗi nhãn mang ~12 điểm sát biên phía phần tách (`pts`), mỗi điểm bỏ phiếu cho mảnh gần nhất (BVH) — một
    điểm "tip" sai khi cắt lồng nhau (đầu mút yếm trước nằm trên hộc đồ đã cắt trước).
  * Trái / phải theo NGƯỜI XEM (X < 0 = trái) như bước đặt tên — Claude từng gọi tay ở X < 0 là "tay phải".
- **XEM CẢ MODEL trước** (2026-10-07, `wc/structure.py`, `planner.structure`, `run.py struct`, addon `start_struct`):
  gấu đi xe Tripo 24 part (`BearOnScooter3dModel1`) — part Tripo KHÔNG khớp bộ phận: "đầu" chỉ là vỏ mũ trùm có tai, MẶT
  dính THÂN, cánh tay liền bàn tay. Xem từng mảnh riêng không thấy "mảnh này phải GHÉP với mảnh kia" → người dùng: "phải
  tạo hình đúng đầu con gấu, tách đầu và thân; tay tách tay và bàn tay; dùng được với các model khác". Vòng lặp:
  `cli struct-views` (6 góc, mỗi mảnh một màu, MÃ MẢNH in ngay trên phần nhìn thấy của mảnh — tia từ phía camera trúng
  mảnh đó trước tiên; `sheet.png`; `pieces.json`) → Claude (mức plan) đối chiếu BỘ PHẬN CHUẨN (đầu = một khối tròn vẹn;
  tay = cánh tay + bàn tay; chân = chân + bàn chân/giày; xe; đồ vật) → `struct_plan.json` {split [{piece, want, parts}],
  merge [{pieces, label}], rename} → addon: đổi tên, GHÉP (`_merge_pieces`: gộp lưới + `voxel_rebuild` cạnh/140 = một
  khối tròn, màu theo mảnh lớn nhất, plan.json ghi merge + remesh), TÁCH qua `start_refine(hints=...)` (Claude chọn ô
  ứng viên nếp theo yêu cầu, mức "pick" = sonnet) → xem lại (`wc_refine_rounds` lần, mặc định 3; không còn tách thì
  dừng). Mảnh vừa yêu cầu tách không được ghép cùng lần (lần sau ghép phần đã tách, vd vỏ mũ + mặt = đầu). Luật cấm ghép
  tấm / khung / nhãn trang trí trên mặt khối (Claude từng định ghép tấm hông thùng hàng vào thùng). "Claude tách sâu"
  không chọn gì = vòng này; chọn mảnh = chỉ xem riêng các mảnh đó.
- Thử trọn vòng trên `BearOnScooter3dModel1` (2026-10-07, 738 s, 27 → 37 mảnh): lần 1 tách mặt / thân ở cổ, bàn tay ×2,
  bàn chân ×2, yên, ghi đông, chắn bùn trước; lần 2 GHÉP vỏ mũ có tai + mặt = "P01 đầu" (một khối 21k mặt), tách cổ lái;
  lần 3 tách sàn chữ L, nắp thùng. Op `crease` Claude TỰ chỉ điểm (`seed_r` > 0) mà biên cắt nằm trên nếp < 35% (thùng
  trơn không rãnh nắp: Laplace trượt xuống mép đáy, "nắp" thành cả cái thùng) → cắt PHẲNG giữa hai nhóm điểm, pháp tuyến
  bám trục thế giới nếu lệch < 25°. Thử headless bằng code addon: `register()` + `start_job` giả chạy `run.py` đồng bộ
  (scratchpad `_tmp_struct_e2e.py`); nhớ dọn cảnh mặc định (Cube, Light) không thì ảnh có khối trắng lạ.
- **Có nên cho Claude xem LƯỚI (wireframe) không?** (người dùng 2026-10-07, ảnh lưới quad Tripo) — không thêm vào bước
  mặt trước (ảnh tô bóng đủ để nhận mặt). Tripo xuất quad nhưng GLB luôn là tam giác; ghép cặp lại thì cả model 85% quad,
  74% đỉnh bậc 4 — nhưng đúng các part cần cắt (mũ, mặt + thân, tay) chỉ còn ~50% đỉnh bậc 4 (part Tripo cắt ngang lưới
  + prep), không còn vòng cạnh khép kín nào; chân thì sạch (95%). Sau bo cong (voxel) mất hẳn. Ảnh lưới mảnh 10k mặt ở
  700 px là nhiễu. Thông tin lưới cho thấy (vòng cạnh dồn ở cổ / cổ tay / vành mũ) chính là NẾP — `crease` đo được trên
  mọi kiểu lưới. Nếu sau này cần: dùng vòng cạnh quad làm ứng viên cắt khi mảnh còn ≥ 85% đỉnh bậc 4 (scratchpad
  `_tmp_loops.py` có bản thử).
- **Thử**: `claude.json` (câu trả lời thô) lưu trong `refine/<mảnh>/`; scratchpad `_tmp_replan.py` dựng lại
  refine_plan.json từ đó không gọi Claude; `_tmp_refine_exec.py` cắt + bo + đặt tên y như addon rồi chụp. Số ứng viên
  đổi khi sửa code dò nếp → claude.json cũ trỏ nhầm ô.
- **Tự động**: "Tách bộ phận + đặt tên" xong → tách sâu (`wc_autorefine`, mặc định bật); chuỗi tự chạy: mặt trước →
  tách → tách sâu → decor. "Claude chia mảnh đang chọn" nay cũng đi đường này (ứng viên nếp + yêu cầu, `--force`, 1 vòng).
- Gấu đi xe 2026-10-06 (P01 2740 mặt): 20 ứng viên 10 s — mũ + tai, thân dưới cổ, quần, từng chân, từng giày, TỪNG TAY,
  từng tai, mõm. Thân xe P06: đầu xe, yên, thân sau + yên, chắn trước + cổ lái. Hộp, bánh xe: 0 ứng viên.

## Tách vỏ + dựng phần bên trong (2026-10-07) — `wc/shell.py`, op `shell`, nút cùng tên ở bước 3
Tripo đúc lớp ngoài thành KHỐI ĐẶC úp lên mảnh trong (gấu đi xe `BearOnScooter3dModel1`: mũ P01 là vòm đặc, mặt gấu là
phần trên của THÂN P06, trong mũ không có đầu) → gỡ mũ trong game chỉ còn mặt cắt nghiêng. Chọn mảnh vỏ (+ Shift-click mảnh
trong, hoặc để tool tự chọn mảnh chạm vỏ nhiều nhất), hộp thoại hỏi độ dày (mặc định 4% cỡ vỏ = 0,25):
1. CỔ = `TM.snap` quanh đáy vỏ − 0,15 chiều cao vỏ, theo trục tâm trong → tâm vỏ; cắt `plane_cut` local (nắp có mã → bo cong).
2. PHẦN TRONG = (vỏ co vào t) ∪ (vỏ ∩ mặt nở ra 1,25 t) ∪ mặt. Co / nở = voxel → Displace pháp tuyến → voxel (`_offset`).
3. VỎ = vỏ gốc − phần trong (Boolean EXACT): rỗng, hở chỗ úp lên mặt, mặt ngoài giữ bề mặt Tripo; vành miệng mang mã cắt.
Gấu: vỏ 9,9 + trong 35,8 = mũ + mặt 45,75 (khít, không chồng); 4 s lõi, ~28 s cả nút (bo cong + trải UV 3 mảnh).
- Đã thử và BỎ: Solidify thẳng mặt Tripo vào trong (tai mũ mỏng < 2t tự cắt nhau → Boolean hỏng, voxel cứu thì lấp đầy
  lòng mũ); tấm đáy bằng Solidify mảng tiếp xúc (`use_even_offset` đẩy đỉnh góc nhọn xa 7 đơn vị); nở 1,15 t (khe mỏng →
  vỏ hở); 1,5 t (ăn mất mép vành mũ trên mắt → viền be + gờ trán khi gỡ mũ). Vỏ/trong hở thì tự thử 1,5 t rồi 1,8 t.
- `contact` chỉ xét dấu trong/ngoài khi gần (< 4 eps): ở xa, điểm gần nhất rơi vào cạnh → pháp tuyến sai dấu → mẩu nhỏ cạnh
  mũ (P02) bị tính "chạm" nhiều hơn thân.
- Điểm neo của op = đỉnh XA các mảnh khác nhất (`_far_anchor`): tâm mặt lớn nhất của mũ nằm đúng mặt tiếp giáp mũ/thân →
  Cắt lại toàn bộ chọn nhầm. Miếng dán D của mảnh trong chuyển sang mảnh mới gần nhất; Hoàn tác trả lại (`UNDO[-1]["hosts"]`).
- Còn lại: khe ngang trán (khoảng trống giữa vành mũ và mặt có sẵn ở model Tripo) vẫn thấy khi gỡ mũ.

## Tab "Đã làm" (2026-10-07) — `wc/library.py` (không cần bpy), panel `WC_PT_library`, `wc_step` "LIB"
Hàng nút bước nay 2 hàng: 1 · 2 · 3 · 4 · Tất cả / Đã làm · Cài đặt. Chọn "Đã làm" tự quét `work/` (`_step_changed`):
mỗi model = trạng thái (Trống / Mới chuẩn bị / Đã tách / Đã xuất FBX), file gốc (còn / mất), xoay / lật, số mảnh M·S·D,
thay đổi (`ops_summary` plan.json: chia · ghép · xoá · mesh lại · tách vỏ · tô màu), đặt tên / decor, chỉnh tay, FBX, dung lượng.
- **Xem model gốc**: `_view_source` = `import_model` + xoay / lật + co cạnh dài 10 + tâm X/Y 0 + đáy Z 0 → TRÙNG chỗ các mảnh
  (xe bus: [−5; −2,99; 0]..[5; 2,99; 5,99] = khung bao prep.json), bật/tắt collection để so trước/sau.
- **Mở mảnh đã tách**: đặt `wc_model` khi TẮT tạm `wc_autoload` (không thì tự nạp + tự chạy chuỗi mặt trước → tách),
  đặt `wc_name`, `wc_turn`, `wc_tilt` theo prep.json (lệch là Tách chuẩn bị lại), nạp `parts_edit.blend` > `parts.blend`.
- **Dọn file tạm** (`library.clean`): PNG render từng góc, ảnh decor / tách sâu (refine/, struct/), `.blend1`, blend đầu vào
  Claude (`struct_in`, `refine_in`, `parts_decor`, `piece_ai`). GIỮ `plan_*.png`, `facing.png`, `parts_sheet/_all/_ids_all.png`
  (nút đặt tên / tô màu đọc lại mà không cắt lại). Đo 2026-10-07: 34 model 1,1 GB, file tạm 603 MB (54%).
- **Xoá** (`library.delete`): `work/<Ten>` (+ `out/<clean_name>.*` nếu tick); `work_dir` chỉ nhận thư mục con trực tiếp của
  work (chặn "", "..", "../out", "a\b"); KHÔNG xoá file gốc (Downloads / inbox); chặn khi việc nền đang chạy đúng model đó.
- **Tích nhiều model** (`WCLibItem.pick`, giữ qua lần quét lại): "Tích tất cả / Bỏ tích", "Xoá N model đã tích", "Dọn tạm";
  `lib_clean` / `lib_delete` có `scope` SEL | PICK | ALL (xoá không có ALL). Hộp xác nhận liệt kê từng model + MB, model
  đang chạy việc nền bị bỏ qua và báo lại.
- Thử bằng cách trỏ `library.WORK` / `OUT` sang bản sao trong scratchpad — đừng thử Dọn / Xoá trên work thật.

## Tách hàng loạt (2026-10-07) — `run.py auto`, khung "Tách hàng loạt" đầu tab Đã làm
Người dùng: "ném nhiều model vào, nạp lần lượt và tách, sau đó t vào soát, tách tiếp để xuất FBX". Thêm file: nút "Thêm
file…" (chọn nhiều), "Thêm thư mục…", hoặc KÉO THẢ vào khung 3D (`WC_FH_queue`, FileHandler → chọn "WoolCut: thêm vào
hàng đợi tách"). Hàng đợi = `sc.wc_queue` (đường dẫn, tên = `model_name`, trạng thái chờ / đang chạy / xong / lỗi / bỏ qua).
- Mỗi file: `run.py auto --in F --name T` = tìm mặt trước (`planner.facing`; hỏng thì inbox −90, web 0) → `split_cmd
  --parts-only` (chuẩn bị, tách theo part, tô màu nếu ô bước 3 bật, Claude đặt tên) → `AUTO_READY:`. Đã có parts.json →
  `AUTO_SKIP` (không ghi đè kế hoạch / chỉnh tay) trừ ô "Làm lại model đã tách" (`--force` + `--reprep`).
- Chạy trên Ô VIỆC NỀN RIÊNG `JOBS["batch"]` → nút khác không bị khoá, soát model đã xong trong lúc chờ. Xong một file thì
  `done` hẹn timer `_queue_next`. "Dừng" = `taskkill /T /F` cả cây (Blender nền + Claude con), mục đang chạy về "chờ".
- Đo: FoxMailCarrier (inbox) 111 s cả lần 2 bỏ qua: mặt trước −90, 16 khối, 27 mảnh, đặt tên đọc prompt từ tripo.json.
- Thử addon ở Blender nền: timer không chạy → gọi tay `woolcut._tick("batch")` + `_queue_next(sc)`.

**Chạy trọn tới FBX nháp** (2026-10-07, ô "Chạy trọn tới FBX nháp + chấm điểm", `auto --full`): tách bộ phận xong
(`--no-paint`: tô SAU tách sâu cho mảnh mới đúng màu) → `cli chain` = Blender NỀN `register()` addon rồi
`woolcut.headless_chain`: `load_parts` → `start_struct` (xem cả model + tách sâu, `wc_refine_rounds` vòng) →
`bpy.ops.woolcut.paint_ai` (nếu ô tô màu bật) → `load_decor_items` + `bpy.ops.woolcut.decor_ai` (mọi decor tick) → ghi
`parts_edit.blend` (đã có thì `parts_auto.blend`, không đè bản người dùng). Mẹo: `start_job` bị thay bằng `_sync_job`
(chạy run.py tới hết rồi gọi `done` ngay — Blender nền không có timer), nên dùng ĐÚNG code của panel. Rồi `export --out
work/<Tên>/draft --kind` → `AUTO_SCORE: 82 Cần xem`, `AUTO_DRAFT:`. Một bước lỗi không bỏ cả model (`AUTO_NOTE`).
`run_blender` nhớ dòng `KHOÁ: giá trị` cuối (`run.LAST`) — dòng của việc lồng nhau thụt lề nên không lẫn.
Mở model ở tab Đã làm = nạp `parts_edit` = bản nháp. `load_parts` nay bỏ decor trong file có `wc_decor_uid` nằm trong
decor.json trước khi đặt lại (trước đó mở parts_edit có decor bị NHÂN ĐÔI decor).

**Thanh xử lý** (2026-10-07, người dùng: "khi tách hàng loạt nên có processing"): `run.stage(k)` in `STAGE: <bước>`
(tripo, facing, prep, plan, cut, paint, label, refine, decor, export, telegram; chuỗi nền in từ `headless_chain`);
luồng đọc output của `start_job` ghi `J["stage"]`, `J["stage_t"]`, và `J["pct"]` từ dòng `[tripo] running 45%`.
`_queue_plan` = các bước dự kiến theo thiết lập hàng đợi → % trong mục = (thứ tự bước + thời gian trong bước /
`STAGE_SECS`) / số bước; còn lại = trung bình các mục đã xong lần này (`WCQueueItem.secs`), chưa có thì cộng
`STAGE_SECS`. Vẽ bằng `layout.progress` (Blender 4.0+, cũ thì nhãn %): hai thanh ở khung hàng đợi (tổng + model đang
chạy), một thanh gọn ở đầu panel mọi tab khác; dòng trong danh sách hiện tên bước thay "đang chạy". Nhãn việc chính
("Đang chạy split · Tách bộ phận 1:23") cũng dùng `STAGE`.

**Model nặng / treo** (2026-10-08: VoxelClown 1,97 triệu tam giác chạy 3 giờ, riêng tách sâu mảng tóc 1,2 triệu mặt
mất 1 giờ 48 phút; CuteDragon .glb 57 MB treo ở chuẩn bị 2 giờ, 3 lần):
- `prep._decimate`: tổng > `TRI_MAX` 150k tam giác → Decimate collapse (giữ UV để đọc màu) về ~`TRI_TARGET` 60k
  ngay sau khi nạp. VoxelClown: giảm trong 28 s, cả chuẩn bị 6 phút.
- `STAGE_LIMIT` 30 phút / bước hàng đợi: `_tick("batch")` giết cả cây, mục thành "lỗi: quá 30 phút ở bước X", chạy
  model sau.
- `REFINE_MAX_FACES` 200k: `start_refine` bỏ qua (đánh dấu `wc_refined`) mảnh nặng hơn.

**Giữ nguyên hình part, chỉ sửa gần chỗ cắt** (2026-10-08, người dùng: "mặt gần phần cắt thì sửa, không liên quan thì
giữ nguyên, vẫn cần fill kín"). Đo trên mảnh cắt thật (SnowBearChef, xe máy): bo cong voxel cũ dựng lại CẢ mảnh — giữ 0–22%
bề mặt xa mép, số mặt ×3,7; `fillet_geo` cục bộ bo được 15/16 nhát, giữ 94–100%, số mặt gần như không đổi. Nay
`fillet.fillet` = `fillet_geo` (nhát hỏng để mép vuông, mảnh vẫn kín); bản cũ còn tên `fillet_voxel`.
→ CÙNG NGÀY người dùng: "chia mảnh xấu hơn trước" (nút Chia, Lát dọc 3): `fillet_geo` trên vỏ mỏng ra mép vuông, khấc,
vành răng cưa. Nay `fillet.fillet` = GHÉP LAI: `fillet_voxel` cả mảnh (mép tròn như trước) rồi `_stitch` — s = khoảng
cách tới mặt nắp (BVH các mặt cap, kể cả nắp cong của cắt theo nếp); giữ lưới GỐC ở s ≥ 2,2 w, lưới voxel ở s ≤ 1,85 w
(`_iso_keep` cắt theo đường đồng mức, nội suy trên cạnh), `bridge_loops` nối từng cặp vòng (ghép theo tâm gần nhất) →
kín + thể tích lệch < 3% + cùng số khối, không thì dùng bản voxel. Mảnh nằm trọn trong dải → bản voxel. Đo: nút Chia
đầu giữ 88% đỉnh gốc, vỏ áo 75% (voxel 0%), không còn vệt lỗ của voxel; cắt cả model SnowBearChef 10/10 nhát, xe máy
4/6 (2 nhát lệch số vòng → voxel). Bẫy: bmesh `verts.index` của đỉnh mới tạo chưa đúng → phải `index_update()`. Chuẩn bị:
khối lưới hỏng → `prep.local_close` (gỡ một vòng mặt quanh cạnh hỏng rồi lấp lại, giữ phần còn lại) trước khi remesh;
nhánh voxel còn lại bỏ Taubin, ép đỉnh về bề mặt Tripo gốc. `_clean_parts`: part hở → `local_close` → `solid_inward`
(Solidify offset −1, bề mặt gốc đứng yên) → voxel cuối cùng; vật mỏng đã kín giữ nguyên. Kết quả: SnowBearChef 3/3 khối
hỏng vá tại chỗ, 41.856 → 28.262 tam giác khi xuất, 92 Đạt; xe máy 32.762 → ~17k.
**Kiểu mép cắt "Mép vát (như BearArt)"** (2026-10-08, ô ở bước 3 cạnh "Bo cong", `wc_cut_style`; mặc định vẫn bo tròn).
Phân tích BearArt (80 mảnh S/M, 99 cặp múi cùng màu chạm nhau): mỗi múi 42–126 mặt, 81–98% tứ giác, nắp PHẲNG (lệch
~0,2% cỡ), mép vát MỘT nấc 45° sâu ~0,21% cỡ, khe giữa hai múi 0,2–0,3% cỡ, vùng cắt chỉ 8–17 mặt. FBX gốc 48–67
byte/tam giác; FBX của tool 38–52 → dung lượng gần như tỉ lệ số tam giác. `fillet.chamfer`: bmesh bevel 1 nấc trên
cạnh nắp|mặt thật (rộng `CHAMFER_W` 0,025 ở cỡ 10), lùi nắp `CHAMFER_GAP`/2 tạo khe, vòng vát mang mã `CHAMFER_ID`
6000 → cạnh sắc nắp | vát | mặt như BearArt. `fillet.fillet(style=)`; tiến trình nền đọc `WOOLCUT_CUT_STYLE` (panel đặt
trong `_env`; `headless_chain` chép vào cảnh). Đo nút Chia 3 lát: đầu 5.846 → 2.644 mặt, vỏ áo 14.508 → 7.734, giữ 100%
đỉnh gốc; sau xuất tối ưu 0,2%: đầu 1.606 → 1.254, vỏ 3.790 → 3.342. Bẫy: `optimize._deviation` cắt
`a.vertices[::k]` — bpy_prop_collection không cắt có bước (mảnh > 3000 đỉnh lỗi) → dùng `foreach_get`.

**Vân len thẳng — UV khối hộp** (2026-10-08, người dùng: "chỉnh uv để texture đi đẹp hơn", ảnh vali). Đo HƯỚNG vân
(`uv.knit_direction`: góc giữa +V và trục gần nhất — đứng hoặc ngang — trên mặt đứng): bộ gốc chỉ có vân ĐỨNG (~0°)
hoặc NGANG quanh thân (~90°), độ xiên trung vị 2–21°; vali của tool 15–33°, 63–88% diện tích xiên > 20° (bím len chéo).
Nguyên nhân: 1 đảo / khối, bộ giải UV uốn dải quanh thân thành vòng cung. `uv._box_uv` (khối có ≥ 20% diện tích mặt
ngang |n.z| > 0,85, dài hay không): mặt trên / đáy chiếu phẳng (u = x, v = ±y); dải quanh thân V = CAO ĐỘ THẾ GIỚI ×
mật độ (vân đứng tuyệt đối, hàng mũi khớp giữa các mảnh kề), U = quãng đường vòng quanh thân (chu vi ở giữa chiều cao
theo góc quanh tâm, 144 ô), đường nối phía sau (+Y); cụm trên/đáy < 5% diện tích nhập vào dải. Vali: xiên 29° → 16°,
nắp 15–33° → 19–20°, méo góc 2,7°, 0,8 s. `unwrap_v2` nay dùng cho UV TRONG CẢNH (`look.apply_piece`, `plan.execute`
— cắt cả CuteToyPlant: méo 4,5°, lệch 2,4%, 44 s) và Xuất FBX tối ưu; nút xuất cũ vẫn `unwrap` cũ. Nút bước 3 "Trải
lại UV (vân len thẳng)" (`woolcut.reuv`, mảnh chọn hoặc tất cả S/M, Ctrl+Z được) cho model đã làm.
**Nắp vali gợn sóng** không do cắt: model chuẩn bị 2026-10-07 bằng code CŨ (voxel + làm dày) → nắp lệch .glb (52% đỉnh
khớp, lệch tối đa 0,31); chuẩn bị mới trùng .glb 100% (lệch 0,0003). Ghép lai giữ nguyên phần xa mép (lệch 0,000).

**Lỗi lỗ / tam giác gập khi chia lưới 3×3 thân vali** (2026-10-08, người dùng gửi ảnh 2 lần): `bmesh.ops.bridge_loops`
trong `_stitch` nối lệch vòng → dải nối XOẮN → tam giác lớn (0,3–1,0) bị gập, mà kiểm tra cũ (kín + thể tích ±3%) vẫn cho
qua. Nay `_zipper` (khoá kéo: `_ring` lấy thứ tự đỉnh, cùng chiều theo Newell, bắt đầu cặp đỉnh gần nhất, tiến theo tỉ
lệ chiều dài cung) + `_folds` (mặt có pháp tuyến ngược trung bình mặt kề, diện tích > 0,05 w²) → có gập thì dùng bản
voxel. Đo trên thân vali chia 3×3: bước nối cũ 34 mặt gập lớn (đúng ảnh người dùng), nay 0 (8/9 ô lùi voxel — khối hộp
đường đồng mức gấp khúc, khoá kéo cũng gập; ô voxel nhìn sạch như trước).
**Điểm neo thao tác chia / ghép**: `_piece_anchor` (tâm mặt lớn nhất) của nắp vali là mặt đáy TIẾP GIÁP thân → "Cắt lại
toàn bộ" áp lát dọc nắp vào THÂN (kết quả khác hẳn cảnh). Nay `_split_op` và hai chỗ ghép dùng `_far_anchor` (đỉnh xa các
mảnh khác / mảnh không ghép nhất). plan.json đã ghi trước đó vẫn mang neo cũ.

**Cắt tỉa phần dư + part không rõ** (2026-10-08, người dùng: "các part tách ra nên cắt tỉa mesh dư, bo kín... bánh xe có
phần dư thì cắt đi... chi tiết thừa cắt bỏ và mesh lại... part không định hình được thì log để t ẩn"). `wc/trim.py`:
- `thin_mask`: mặt MỎNG = tia vào trong (−n) chạm mặt đối diện NGƯỢC hướng trong `THIN_REL` 1,2% cỡ. `trim`: bỏ cụm mặt
  mỏng ≤ `max_comp` diện tích, vá kín tại chỗ (`prep.local_close`), Taubin chỉ đỉnh vá; part > 35% mỏng (lá, ốp hông
  48–49%) không đụng. Tự động trong `plan.execute` trước bo cong với `AUTO_COMP` 3% (gai bánh trước 1,3% → sạch); vạt
  lớn hơn (phuộc 6–16%) để Claude quyết — vành mũ / tai mỏng là chi tiết thật.
- `clean_part` (phép mở `shell._offset` co/nở bằng voxel remesh): KHÔNG bắt được vạt nhàu (phuộc trái 0% — offset vào trong
  làm vạt lộn trái rồi OpenVDB vẫn tô đặc) → thay bằng `repair` dưới đây; `clean_part` chỉ còn cho mã cũ.
- **Sửa part xấu** (người dùng: "tool tự detect các part xấu và sửa lại hoặc ẩn đi"), `trim.repair`:
  - `excess_voxel`: tự VOXEL HOÁ (tia chẵn lẻ 3 trục, bầu 2/3 — pháp tuyến lật ở vạt nhàu vẫn đúng; ~72 ô theo cạnh dài,
    0,1–1 s/part) → bán kính dày nhất R (số lần co) → MỞ trên lưới với ro = 0,45 R (xen chữ thập / khối 3×3×3) →
    khoảng cách từng mặt tới thân đã mở. DƯ = cụm mặt ngoài vùng max(2, 0,8 ro) ô (góc hộp bị phép mở bo lùi 0,4–0,7 ro)
    VÀ nhô xa ≥ ro + 3 ô; loang tới mặt kề còn nhô ≥ 2 ô (cắt sát gốc). Không đo: hở, ro < 2 (R ≤ 3 ô, mỏng đều: ốp hông, cổ xả).
  - Thử (1) `_cut`: bỏ mặt dư, gỡ "tai" mép lỗ (mặt ≥ 2 cạnh biên), khối lớn nhất, `local_close(max_loop=6000)`,
    `relax_fill` (chia nhỏ quạt vá + Taubin, viền giữ yên → không chóp sao) + bỏ gai sót (`trim` 5%). (2) `remesh_core`:
    khối ô của thân đã mở → voxel remesh 0,75 ô → Taubin → BÁM lại bề mặt gốc ≤ 1,5 ô (chỉ mặt sát thân ≤ 1 ô; bám cả gốc
    kim thì vây hiện lại dọc phuộc) → giảm mặt 1,2×. `_good`: kín, ≥ 40% diện tích, ≤ 1% diện tích xa thân (`far_frac`
    theo trường khoảng cách bản gốc), mỏng (< ro) không hơn bề mặt giữ lại + 3%, góc gập > 60° ≤ 8% (nắp ống 90° là bình
    thường — tiêu chí "lởm chởm" cũ loại nhầm bản cắt sạch của mặt nạ), ĐO LẠI `excess_voxel` ≤ 3%. Cả hai trượt → "xau".
  - Xe máy: tay vịn / tay lái / ốp thân / thân sau → cắt; mặt nạ (bỏ 2 chân), bình xăng, sàn để chân, động cơ, hai phuộc →
    mesh lại; đèn pha → xấu (ẩn). Dư > 50% (`EX_MAX`) = part mỏng đều → không tự sửa.
  - BẮT NHẦM chi tiết thật mảnh hơn thân: tay cầm cán bột, quả nụ, vành mắt robot, gọng kính, yếm tạp dề, cành hoa (gấu /
    thỏ / cây / robot 13 mảnh) → đo hình học KHÔNG tự áp; chỉ (a) vẽ `struct/excess.png` (phần sẽ cắt tô ĐỎ, `structure.
    excess_sheet`, dòng pieces có `[excess.png: đỏ x%]`) cho Claude duyệt, (b) nút "Tìm part xấu" đưa vào danh sách cho
    người dùng xem.
- Claude "xem cả model" (`STRUCT_RULES` mục 4–6): `"trim"` → `_apply_trim_hide` → `_repair_one` (repair; không thấy dư mà
  Claude bảo có → `trim(relative=0.5)`) → `_replace_tm` + plan op `trim` (replay = `repair`) + Hoàn tác; sửa không đạt →
  ẩn. `"hide"` (rách nát, cứu không được, bỏ đi model vẫn đọc được) → `_hide_piece`. Trước đây "trim" tách theo nếp thành
  [`TRIM_LABEL`, tên cũ] → nếp đặt quá cao, phuộc phải giữ gần hết vạt; `_drop_trimmed` chỉ còn cho kế hoạch cũ.
  `"unknown"` → `work/<Tên>/unknown.json`. Khung bước 3 "Part không rõ / xấu": chọn / cờ lê = sửa / mắt = ẩn-hiện / tích =
  đã xem; mảnh ẩn qua plan.json (tên mới sau cắt lại) vẫn hiện trong khung (`wc_hidden_why`). Ẩn = `wc_hidden`: giấu khung
  nhìn, KHÔNG xuất (`export.run`), không chấm, không đưa vào ảnh xem cả model / tách sâu; plan op `hide` / `show` (Piece.hidden
  → `wc_hidden` khi xuất parts.blend) nên "Cắt lại toàn bộ" vẫn ẩn.
- Nút bước 3: "Tìm part xấu" (`woolcut.find_ugly`) và "Sửa mảnh chọn" (`woolcut.trim_piece`, `piece=` cho dòng danh sách).
- Chưa làm: quạt vá lỗ ở BƯỚC CHUẨN BỊ (`prep.local_close` trong `_clean_parts`) vẫn ra chóp sao (thân sau, đuôi xe) —
  `relax_fill` mới chỉ dùng trong `_cut`.

**Part chồng lấn** (2026-10-08, cáo trượt ván — GLB 73 khối rời cắm chồng vào nhau; người dùng: "các part k nên overlap
lên nhau quá nhiều", "overlap nhiều thì nên cân nhắc gộp lại"). Đo trên parts_edit: bàn tay chìm 24% trong ống tay áo,
đùi 43% trong vạt áo, khăn 45% trong thân áo, đế giày 78% trong lưỡi trượt. `wc/overlap.py`, chạy trong `plan.execute`
sau `review`, trước bo cong (toggle panel `wc_overlap` → env `WOOLCUT_OVERLAP`, plan `"overlap": false` tắt):
- `inside_frac(a, b)`: diện tích mặt a nằm TRONG khối kín b (điểm gần nhất + pháp tuyến; khối của plan có pháp tuyến ra
  ngoài — parts.blend sau xuất thì KHÔNG, đo lại ở đó phải dùng tia chẵn lẻ). Bỏ qua D và hai mảnh chung mã nắp (anh em
  một nhát cắt). Xử lý theo f giảm dần, đo lại trước mỗi cặp.
- f ≥ `MERGE_FRAC` 0,6, hoặc ≥ 0,3 + cùng màu + nhỏ ≤ ½ mảnh bao (đầu gối trên đùi) → GỘP (Boolean UNION, `_union_ok`
  kiểm diện tích). Mũ + vành mũ cùng đỏ, chìm 31–36%, cỡ gần bằng → KHÔNG gộp (là hai bộ phận). 0,6 chứ không 0,7: lưỡi
  trượt chìm 67% cắt ra lát mỏng.
- Còn lại ≥ 5% → CẮT phần chìm (Boolean DIFFERENCE EXACT): nhìn ngoài không đổi, hai mảnh áp sát. Boolean hỏng (lưới
  Tripo tự cắt nhau: ra 0–2% diện tích) → nhận ra bằng diện tích còn < 0,6 (1 − f) → `_cut_faces` (bỏ mặt chìm + vá như
  `trim._cut`), không gộp nhầm. Mặt tiếp xúc mới cap = −1 (không bo cong).
- Cáo: cắt 27–36 mảnh, gộp 4–5; chồng sâu > 3% từ 53 cặp → 14 cặp; ~40 s cả bước cắt.

**Cáo DJ: áo khoác sai tên + sai màu, decor méo** (2026-10-08, người dùng: "detect sai áo khoác, tách sai"; "mesh decor
khi tách ra nên xem lại, tinh chỉnh mesh cho hợp lý"):
- Claude đặt tên: mảnh chứa ÁO KHOÁC gọi "bàn tay phải" (tách bàn tay ra → "cánh tay phải" 13.534 mặt), khối đầu + thân
  gọi "mũ lưỡi trai". `structure._flag_names`: tên chi tiết nhỏ (tay, chân, ngón, mũ, tai, mắt, nút...) mà ≥ 12% thể
  tích hoặc tay / chân VẮT NGANG giữa thân → dòng `[NGHI SAI TEN: …]` trong prompt xem cả model + luật 3 bảo xem kỹ.
  (Dòng `[excess.png: đỏ x%]` lần trước KHÔNG vào được prompt — thay chuỗi trong heredoc trượt im lặng; nay sửa.)
- `_name_pieces` ĐẢO TÊN sau khi tách theo nếp: điểm mẫu phía phần tách ("part") và phía còn lại ("rest") chỉ cách nhau
  0,03–0,05; bo cong xong mặt gần nhất có thể thuộc mảnh bên kia → "đầu" (z 3,2–5,3) ↔ "thân". Nay planner gửi kèm
  `rest_pts`, so TƯƠNG ĐỐI (khoảng cách tới điểm part − tới điểm rest) → tái hiện trên refine_plan cáo DJ: đúng.
- Chuỗi tự chạy panel: tô màu chạy lúc TÁCH BỘ PHẬN, trước xem cả model / tách sâu → mảnh con giữ màu mảnh cha (áo khoác
  màu lông). Nay refine xong → `chain_next("paint")` (WC_OT_paint_ai, done → decor) khi bật `wc_autopaint`. Hàng đợi
  nền đã có paint sau refine.
- Decor tròn: con ngươi Tripo méo, có cục u ở vành; Taubin / chia nhỏ không bào được u, mặt lên 5k. `trim.fit_blob`
  (plan.execute, mảnh D, toggle `wc_decor_fit` → env `WOOLCUT_DECOR_FIT`): thay bằng ELIP 24×12 (528 mặt) khớp tâm, trục
  PCA, bán kính nửa khoảng phân vị 1–99 — chỉ khi trục phụ/chính ≥ 0,75, thể tích/elip 0,6–1,4, trung vị lệch ≤ 0,2:
  con ngươi, mũi, nút áo, nút mũ, núm; vạch, cần gạt, đế giày, túi, viền tay áo, nơ giữ nguyên (cáo DJ: 19 mảnh).

**Mảnh không rõ là gì → XOÁ** (2026-10-08, người dùng: "những mesh k có hình thù cụ thể k detect được nó là gì thì nên
xoá đi"): `"unknown"` của xem cả model → `_drop_unknown`: nhỏ (≤ 4% thể tích VÀ đường chéo hộp bao ≤ 25% cỡ model) →
kho ẩn + plan `drop` + Hoàn tác; to hơn → chỉ ẩn (`_hide_piece`) và hiện trong danh sách "Part không rõ / xấu". Cần CẢ
kích thước: đế DJ to → quần chỉ 1,5% thể tích nhưng 41% cỡ. Luật 5 STRUCT_RULES: đoán được thì rename, đừng đưa vào
unknown (bộ phận thật bị xoá).

**UV bám trục** (2026-10-08, người dùng: "uv vân len phải như đế tròn, tay chân đang lỗi", "đầu cáo chưa đều"; "đế chuẩn
rồi"). Nguyên nhân: (1) unwrap Blender dàn phẳng nửa thân như bản đồ → hàng mũi cong xoáy; (2) nhánh hộp bắt nhầm 30/37
mảnh cáo vì `|n.z| > 0.85` ≥ 20% (vai áo, đỉnh ống quần, mặt tiếp xúc 21–36%) → tay chân méo 13–21°.
- `unwrap_v2`: HỘP THẬT = ≥ 33% mặt ngang PHẲNG `|n.z| > 0.97`, không tính nắp cắt và mặt tiếp xúc (`_contact_faces`:
  sát mặt mảnh khác ≤ 0,1% cỡ) → `_box_uv` giữ nguyên (đế tròn 54%, nắp vali 37–54%, đế giày 70%; đầu 18%, giày 20%).
- Còn lại → `_aligned_uv`: `_axis_regions` chia vùng: LÕI THÂN = khung ngang của 20% chiều cao thấp nhất (gấu áo; 40%
  thì tay buông thấp lọt vào), mặt chìa ra ngoài khung = ống tay → mỗi ống liền mạch một trục (PCA nếu dài ≥ 1,5, ống
  ngắn mập có cổ tay cuộn → hướng NGANG từ trục thân ra trọng tâm ống), mọc ngược vào trong theo mặt cách trục ống ≤ 1,2
  bán kính và lùi ≤ 1 bán kính (không lấn đỉnh vai); còn lại Z; mảnh không có lõi (cánh tay rời nằm ngang) → trục dài.
  Đã thử, không tách được ống tay hoạt hình ngắn mập khỏi vai: độ dài lân cận, ma trận pháp tuyến lân cận, độ dày tia
  (tay 1,1–1,4 so thân 1,75). Thân áo cáo (chữ T): trước cả mảnh theo Z → méo 7,4°, lệch > 2× 11% → bị loại về unwrap cũ
  = lưng XOÁY VÒNG (người dùng chụp); nay 2,4°, 0,5%. Có chia vùng ống thì giải THÊM bản "cả mảnh một trục" (PCA nếu
  dài nằm ngang, không thì Z) và giữ bản điểm tốt hơn (méo + 100·lệch2x + 50·cỡ mũi): đuôi cáo chếch lên (20% thấp
  nhất chỉ ôm gốc → nửa đuôi thành "thân", vân xiên) cần một trục; thân dưới gấu ngồi hai chân chìa ra > 35% cần chia
  vùng (ngưỡng cứng 35% làm gấu tụt 1,8% → 5,2%). Mỗi vùng `_solve_region` bình phương tối thiểu ∇v = trục chiếu lên mặt, ∇u ⊥ (CG
  numpy — Blender không có scipy), chỏm `|n.trục| > 0,75` + nắp cắt chiếu phẳng (để trong phép giải thì cỡ mũi lệch 42%),
  đường nối phía sau, chuẩn hoá cỡ mũi theo trung vị, neo hàng theo mặt đứng (hai nửa đầu khớp hàng giữa mặt).
- So từng mảnh với cách cũ (`_old_unwrap`), giữ bám trục trừ khi tệ hơn rõ (méo +3°, lệch > 2× +5%, cỡ mũi +8%):
  ván trượt gấu dẹt mỏng bám trục hỏng 40°.
- Đã thử, bỏ: chiếu ống thuần u = góc × bán kính (xô 15–17° ở khối tròn); giải u theo ∇v xoay 90° (18–25°); chỏm + dải
  cho unwrap Blender (không đổi số đo).
- Cáo (parts_edit người dùng): cỡ mũi lệch > 25% 8,3% → 2,5%, méo góc 5,5° → 3,3°, lệch > 2× 4,6% → 0,6%; gấu đầu bếp
  4,8% → 3,3%. Nút bước 3 "Trải lại UV (vân len thẳng)" (`woolcut.reuv`) dùng `unwrap_v2`.
**Cỡ mũi len đều** (`score.stitch_spread`, mục bảng chấm khi xuất "Cỡ mũi len không đều" ≤ 15% diện tích lệch > 25% so
trung vị cả model): vali trong cảnh người dùng (Blender chưa nạp lại addon → vẫn UV cũ) 10/12 mảnh ổn, 2 mảnh LỖI GẬP
82–86% (mũi to ×1,6) → "vân to vân nhỏ"; UV mới (`unwrap_v2`) trên vali: ×0,98–0,99, lệch 1–5%.

**Polycount khi xuất**: `export.polycount` → log `[polycount]`, dòng `POLY:`, `score.json["poly"]`, step 4 hiện
"Đã xuất: N tam giác · M mặt (x% tứ giác) · K đỉnh", Telegram ghi số tam giác.
Số đo UV / lưới (scratchpad `uv_metrics.py`): bộ gốc 12–27k tam giác, 82–89% tứ giác, 2,2–3,3 đảo UV/mesh, méo góc
3–6°, diện tích lệch > 2× 0,6–5%; bản của tool 1 đảo/mesh, méo góc 10–14°, lệch 3–12%. Giảm mặt có kiểm sai số
(quadric collapse, kín, lệch tối đa so bề mặt gốc) trên SnowBearChef: 0,1% cỡ → −27%, 0,2% → −44%, 0,4% → −65%.

**Xuất FBX tối ưu** (2026-10-08, nút riêng `woolcut.export_opt`, nút xuất cũ GIỮ NGUYÊN; hai nút dùng chung lớp
`_ExportOp` — đăng ký lớp con của operator đã đăng ký làm hỏng `poll` của lớp cha): `export --optimize <tỉ lệ> --uv v2
--out out/toi_uu` (cùng tên file, thư mục riêng).
- `wc/optimize.py`: mỗi mảnh Decimate collapse, tìm nhị phân tỉ lệ nhỏ nhất mà vẫn KÍN và lệch hai chiều ≤ min(ô "Lệch %"
  × cỡ model, 3% cỡ mảnh) — chạy trước `to_quads`, ở kích thước cuối.
- `uv.unwrap_v2` (A + C): mép phẳng = đường nối; đảo KÍN tròn → tách đôi trước/sau (dẹt → theo mặt dẹt); đảo kín
  DÀI → đường nối dọc phía sau như ống và vân len chạy dọc trục khối (`_fit_islands(axis=)`); đo méo từng đảo (góc > 8°
  hoặc > 5% diện tích lệch > 2×) → bổ đôi theo trục dài của đảo, trải lại (≤ 6 đảo / mảnh).
- Bảng chấm khi xuất thêm "Méo UV (góc trung bình)" ≤ 8° (`score.uv_distortion`, gốc 3–6°).
- Đo: SnowBearChef 41.856 → 11.164 tam giác, UV 13,3° → 7,7°, 76 → 92 điểm; xe máy 32.762 → 18.330, UV 11,0° → 5,7°,
  92 → 100. Ảnh len (scratchpad `render_knit.py`): hình gần như không đổi.

**Ảnh / prompt → Tripo API trong hàng đợi** (2026-10-07): "Thêm file / ảnh…" nhận png/jpg/webp (`src="image"`), nút
"Prompt bước 1" thêm prompt Text → 3D (`src="text"`; prompt ẢNH bị từ chối). `auto --image/--text` gọi
`stages.generate` (tách từ `gen_cmd`) với `--model/--topology/--faces` ở khung (mặc định P2.0 · Quad · 12.000 mặt — ô
`wc_api_faces` riêng, không dùng số mặt bước 2),
in `MODEL_READY:` → panel đổi mục thành file model. **Credit**: "Chạy hàng đợi" có mục ảnh/prompt thì LUÔN mở hộp xác
nhận (số mục + ước tính `tripo.estimate`, nhắc credit API ≠ credit web); chỉ đi qua hộp (`confirmed`) mới có `--yes`.
Không `--yes` → `AUTO_FAIL`. Chống gửi hai lần: `inbox/<Tên>.tripo.json` ghi `source` (đường dẫn ảnh / prompt) →
`stages.reuse_task` lấy lại task (không tốn credit); thêm lại cùng ảnh thì `_tripo_name_for` dùng lại tên cũ. "Thư
mục…" có model thì chỉ lấy model (inbox có ảnh xem trước Tripo).

## Bảng chấm điểm chuẩn game (2026-10-07) — `wc/score.py`, bước 4 "Chấm điểm", tự chấm khi xuất
Đo trên MESH THẬT: `items_from_scene` (panel, cùng luật loại / màu / mảnh chủ với `export.build`, M hở → S) hoặc cây
vừa dựng trong `export.run` (ghi `<Gốc>.score.json` + `work/<Tên>/score.json`, in `SCORE:`). Ba nhóm: GAMEPLAY (M
17–39: lỗi khi < 10 / > 48; màu 8–14: lỗi khi < p10 bộ gốc / > 17; M hở), HÌNH (bộ phận màu ≥ p10, mảng cùng màu ≤
p90 — `sep.SCORE_LIMITS`; decor cách mảnh chủ > 6%), KỸ THUẬT (material có trong Unity, số mesh, tam giác ≤ 38.610,
mảnh S/M < 3%). "Tham khảo" (không trừ điểm): cặp trái/phải khác màu, mảnh không chạm gì, M > 50% cỡ — chấm thử 88
FBX gốc thì bộ gốc cũng phạm 56/35/27 lần. Điểm = 100 − 25×lỗi − 8×cảnh báo; ≥ 85 Đạt. Bộ gốc ra 52 Đạt / 32 Cần xem
/ 4 Trượt (Lv1, FrenchBakery, LV1_update, JollyRoger). Nút xuất: còn LỖI → hộp "Vẫn xuất". Tab Đã làm: cột điểm,
ô xếp theo điểm (thấp trước).

**Tô màu theo bảng chấm** (`_paint_hint`, `planner.paint(hint=)`, `run.py paint --hint`): trước khi tô, chấm cảnh;
mảnh S/M < 8 màu hoặc mảng cùng màu > p90 → lời nhắc "ƯU TIÊN theo bảng chấm (vượt luật giữ màu texture)" kèm danh
sách mảnh S/M theo từng màu. Gấu đầu bếp (texture 4 màu): không nhắc thì Claude giữ nguyên (51 Trượt); nhắc mà không
nói "không tính D" thì Claude đếm cả mắt/nút thành "12 màu"; nhắc rõ → 9 màu S/M, 76 Cần xem. `PAINT_RULES` nay ghi
8–14 màu trên M/S. **Bẫy tên**: mảnh đã đặt tên là "P12 tay phải" nhưng Claude trả "P12" → trước đây khớp 0 mảnh (tô
màu ở cảnh / chuỗi nền đổi 0 màu); `planner.paint` nay khớp theo mã đầu tên.

## Gửi Telegram khi hàng đợi tách xong (2026-10-07) — `wc/notify.py`, tab Cài đặt
Người dùng: "khi tách xong 1 ảnh thì gửi ảnh model tách 6 mặt, ảnh parts_ids_all qua telegram". Preferences: `tg_on`,
`tg_token` (PASSWORD), `tg_chat`; nút kính lúp = `getUpdates` lấy chat id (nhắn /start cho bot trước), "Gửi thử" =
`sendMessage`. Bật thì `_queue_args` thêm `--tg`, token / chat đi qua biến môi trường `WOOLCUT_TG_TOKEN/CHAT` (không
ghi file). `run._tg_report`: một album `sendMediaGroup` (ảnh > 10 MB gửi dạng file) — có bản nháp thì
`<Gốc>_all.png` + `<Gốc>_ids_all.png` của nháp, không thì `parts_all.png` + `parts_ids_all.png`; chú thích = số mảnh
M/S/D, điểm, các mục cần sửa. Tách lỗi → chỉ nhắn chữ. Gửi lỗi chỉ in `[telegram] loi:`, không làm hỏng hàng đợi.
Chưa thử gửi thật (chưa có token của người dùng) — đã kiểm nội dung request bằng giả lập `urlopen`.

## Tự học từ model tốt (2026-10-07) — `wc/learn.py`, `data/good_models.json`
Xuất THẬT (không phải nháp) đạt ≥ 85 → ghi tên, dạng, kiểu prompt (`Decor:` = text, còn lại = ảnh), prompt, điểm, số
đo; xuất lại tụt điểm thì bỏ (trừ khi người dùng tự đánh dấu). Nút "Lưu làm mẫu tốt" ở bước 4 (`manual`). Bước 1
(`prompt.own_examples`) nối tối đa 3 prompt tốt CÙNG dạng + kiểu vào phần ví dụ ("do NOT copy their subject"); panel
hiện "Claude học theo N model tốt". Model không có prompt vẫn được đánh dấu nhưng không góp câu chữ.

## Bẫy đã gặp
- **F3 Reload Scripts KHÔNG nạp lại `wc.*`** (2026-10-05): `fillet.py` mới gọi `plane_cut(shift_rel=)` của `tm.py` cũ → lỗi bị nuốt, bo cong im lặng không chạy. `register()` nay xoá `woolcut.wc*` khỏi `sys.modules`; `fillet()` mặc định in lý do bỏ qua.
- Addon: tiến trình nền kết thúc trước khi luồng đọc output đọc hết → mất dòng `CUT_READY`/`SPLIT_READY` ở cuối →
  không nạp kết quả (người dùng thấy mảnh cũ). `_tick` phải `join` luồng đọc trước khi gọi `done`.
- Ảnh chụp viewport qua MCP không có lớp vẽ GPU của addon (xem trước nhát cắt) — kiểm bằng `_DRAW["calls"]`.
- Nạp `parts.blend` vào file đã có material cùng tên → Blender đổi thành `.001`; mọi chỗ đọc màu dùng
  `std.canonical` / `wc_color`.
- Ảnh prep từng vẽ đè model Tripo gốc lên khối kín → tưởng nhãn màu đúng mà thật ra đã mất mắt. Xoá SRC
  trước khi render.
- `clean_labels` từng nhận diện tích tổng nhân hệ số chuẩn hoá hai lần → mọi vùng thành "đốm" → mất mắt,
  lòng tai.
- Giới hạn 10 màu gộp màu đen của mắt vào xám nhạt → dùng 14 (game cho 8–14).
- Chi tiết tách D trước khi cắt từng bị tô lại màu chính của khối (cam) → băng mũ vàng thành cam, vùng mũ
  co lại. Nay giữ màu gốc (mã `-2-c`).
- Heredoc Python trong Bash tool hay vỡ khi có dấu nháy/`\` → viết bản vá ra file rồi chạy.
- Xuất sau khi nạp `parts.blend` bằng `libraries.load`: `matrix_world` còn cũ (chưa cập nhật) → tâm mảnh tính
  sai, FBX dài 27,5 thay vì 8,2. Gọi `bpy.context.view_layer.update()` trước khi đọc `matrix_world`.
- `run.py ... --in` đường dẫn tương đối bị Blender mở thành `C:\woolcut\...` → `run.py` đổi sang tuyệt đối.
- Đừng xuất lại `out/<Ten>.fbx` từ `parts.blend` khi người dùng đã xuất từ `parts_edit.blend` (chỉnh tay) —
  ghi đè mất bản chỉnh. Kiểm giờ sửa của `parts_edit.blend` trước.
