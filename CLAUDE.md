# MeshForge — ghép model mới từ mảnh đã tách của các file FBX

Thư mục này chứa các file FBX và tool **MeshForge** ở [meshforge/](meshforge/).
Nhiệm vụ: **người dùng mô tả (hoặc để bạn tự nghĩ), bạn ghép một model mới từ các CỤM
mesh đã tách sẵn, và kết quả phải NHÌN ĐẸP.**

## Pipeline

```
FBX thả vào  ──sync──►  quét + đo hình học + TÁCH CỤM + render cụm + Claude ĐẶT TÊN
                                                         │
                                                  data/parts.json   ← thư viện mảnh
                                                         │
mô tả / tự nghĩ ──────►  chọn cụm ─► recipe ─► build ─► CHẤM ĐIỂM ─► lặp ─► FBX
```

Mọi thao tác đi qua một cổng, chạy bằng python hệ thống:

```bash
python meshforge/run.py sync                        # file mới: tự tách + gán nhãn
python meshforge/run.py parts --query "cat head"    # TRA THƯ VIỆN CỤM (dùng cái này)
python meshforge/run.py parts --role head --good    # lọc theo vai trò / chất lượng
python meshforge/run.py clusters --files A,B        # render + sheet cụm để NHÌN
python meshforge/run.py find --shape cone --sheet   # tìm mảnh lẻ theo hình dạng
python meshforge/run.py build --recipe ten          # dựng + preview + 3 BẢNG CHẤM ĐIỂM
python meshforge/run.py recipes --verify            # model nào trỏ tới mảnh đã biến mất
python meshforge/run.py sheet --recipe ten          # soi nguyên liệu của một recipe
python meshforge/run.py files --query kiem          # mục lục cấp file (phụ)
```

## Luật 0 — KHÔNG xoá hay sửa file của người khác

Chỉ ghi đúng file recipe được giao. **Tuyệt đối không** xoá hay sửa bất kỳ file nào
khác trong `meshforge/recipes/`, `meshforge/out/`, `meshforge/data/` hay bất cứ đâu.
Không "dọn dẹp". Đã từng xảy ra: một phiên ghi đè recipe đang dùng rồi xoá sạch thư
mục. Cần file tạm thì đặt tên `_tmp_*.json` và chỉ xoá đúng file đó.

## Luật 1 — làm việc bằng CỤM trong parts.json, không bằng mesh lẻ

`data/parts.json` là thư viện mảnh đã tách. Mỗi mục là một **mảnh nguyên tử**: một khối
trọn vẹn (cả cái đầu kèm tai, mắt, ria) tách tự động rồi Claude đặt tên sau khi nhìn ảnh.

Mảnh được tách theo nguyên tắc **tái dùng nhiều kiểu**, không theo vai trò trong model
gốc: quả cầu vàng ở đầu con gà cũng là quả bóng, cũng là quả táo. Vì thế khi chọn mảnh
hãy tra `uses` chứ đừng chỉ tra `role` — `role` chỉ là cách dùng tự nhiên nhất.

Mỗi mảnh có:

| Trường | Ý nghĩa |
|---|---|
| `name` | tên tả **hình + màu** trước, gốc gác sau: `sphere_yellow_smooth`, `cat_head_whiskers` |
| `shape` | sphere / dome / cylinder / cone / box / slab / disc / ring / tube / rod / blob / sheet / organic / composite |
| `is` | nó là gì trong model gốc: `"chicken body"`, `"neon sign body"` |
| `uses` | **2–5 cách dùng khác nhau** — trường quan trọng nhất khi chọn mảnh |
| `role` | body / head / limb / base / prop / container / furniture / vehicle / plant / food / clothing / weapon / decor / vfx / sign |
| `tags` | từ khoá tìm kiếm |
| `attach` | cụm này thường gắn vào đâu — **đọc trước khi quyết định `attach.to`** |
| `quality` | `good` dùng ngay · `partial` chỉ là mảnh vỏ/cung, cần ghép thêm · `junk` vụn |
| `dim`, `n`, `parts` | kích thước, số mesh, danh sách mesh bên trong |

Trong recipe, tham chiếu cụm thẳng bằng id — **không bao giờ bịa id mesh**:

```json
{"id": "head", "cluster": "Vocalist#06", "attach": {"to": "body", "at": "top", "snap": true}}
{"id": "kit",  "clusters": ["DrumChapter06#02", "DrumChapter06#05"],
               "drop": ["DrumChapter06/S_Drum33"]}
```

`cluster` mở rộng thành danh sách mesh, giữ nguyên vị trí tương đối bên trong — nên
ria vẫn dính đúng đầu khi di chuyển. `drop` bỏ vài mesh không cần. Một model tốt
thường gồm **3–6 cụm từ 2–4 file khác nhau**.

Ưu tiên cụm `quality=good`. Chỉ dùng `partial` khi cố ý ghép nhiều mảnh vỏ lại.
Không bao giờ dùng `junk`. Mesh lẻ (`parts` với `src`) chỉ cho thứ đơn chiếc nhỏ.

## Luật 2 — bắt buộc NHÌN, đừng đoán từ tên

1. `run.py parts --query ...` → chọn cụm ứng viên, đọc kỹ `attach` và `dim`.
2. Chưa chắc thì `run.py clusters --files <File>` rồi **đọc ảnh PNG bằng tool Read**
   ở `meshforge/thumbs/_sheets/_CLUSTERS_*.png`.
3. Viết recipe.
4. `run.py build --recipe ...` rồi **đọc `meshforge/out/<Name>_front.png`**. Đọc
   `front` trước — góc `iso` gây ảo giác về khoảng hở.
5. Lặp tới khi bảng chấm điểm sạch VÀ ảnh nhìn đúng. Thường 2–4 vòng.

## Luật 3 — chấm điểm mối nối bằng SỐ, đừng tin mắt

Ảnh 512px không lộ khe hở 2cm. `run.py build` in bảng:

```
the            gan vao            gap     chim    ti le
head           body             0.000      18%     0.81
stick          paw              0.142       0%     0.35   HO
```

- `gap` — **phải là 0.000**; > 0.02 là hở.
- `chim` — < 1% chỉ chạm vỏ, nhìn nghiêng thấy hở; > 60% bị nuốt.
- `ti le` — > 2.5 thường sai tỉ lệ.

**Luôn bật `"snap": true`** và để `offset` = 0. Chỉnh độ lún bằng `"contact"`
(mặc định 0.55; mảnh con rộng hơn cha như mũ trùm đầu thì 0.9; đặt hờ thì 0.3).
Danh sách **CAN SUA** phải rỗng mới được báo xong.

## Luật 3b — BỐ CỤC: bảng thứ hai, quan trọng ngang bảng mối nối

`build` in thêm bảng **BO CUC**. Nối đúng mà bố cục sai thì vẫn xấu — đây là thứ
phân biệt "các khối dính vào nhau" với "một model được thiết kế".

| Chỉ số | Đạt khi | Ý nghĩa |
|---|---|---|
| `tam khoi (cao)` | ≤ 55% | tâm khối ở nửa dưới → nhìn vững, không nặng đầu |
| `khoi chinh / nhi` | ≥ 1.6× | có một khối chủ đạo rõ ràng, không phải một đống bằng nhau |
| `the khong co diem tua` | 0 | mọi thứ tựa lên một khối, không treo giữa không |
| `the qua nho` | ≤ ¼ số thể | mảnh vụn làm silhouette lởm chởm |
| `so mau` | ≤ 6 | quá nhiều màu cạnh tranh thành một mớ |
| `lech trai/phai` | ≤ 18% | cân đối quanh trục đứng |

Bảng này là một trong ba — xem Luật 3b và 3c.

Cách chữa thường dùng, theo thứ tự hiệu quả:
1. **Phóng to khối chủ đạo** thay vì thu nhỏ mọi thứ khác — model to ra, rõ ra.
2. **Cho mọi thứ tựa lên nhau**: phụ kiện gắn `at: "top"` của một khối, không treo ở
   sườn bằng `[u,v,w]` giữa không khí.
3. **Cặp đối xứng**: thêm bản mirror bên kia thay vì để một mảnh lệch một bên.
4. **Ép màu** cho 1–2 thể để còn ≤ 6 màu, ưu tiên cho khối phụ (giữ màu khối chính).
5. Bỏ hẳn mảnh nhỏ hơn 12% chiều cao nếu nó không đóng góp gì cho silhouette.

## Luật 3c — SILHOUETTE: bảng thứ ba, thứ mắt nhìn đầu tiên

`build` in thêm bảng **SILHOUETTE** — đo trên ảnh bóng đen nhìn chính diện, vì đó là
thứ người ta nhận ra trước cả màu sắc.

| Chỉ số | Đạt khi | Bắt lỗi gì |
|---|---|---|
| `vung roi` | = 1 | hình đứt thành nhiều mảng, đọc ra nhiều vật rời |
| `the bi vui` | 0 | thể bị che còn < 35% diện tích của chính nó — coi như không tồn tại |
| `do dac (bao loi)` | ≤ 0.93 | bết thành một cục tròn, không có hình |
| `ti le khung` | tham khảo | cao/rộng của silhouette |

Cách chữa: thể bị vùi thì **dịch ra ngoài hoặc bỏ hẳn** (giữ lại chỉ tốn poly); hình
đứt thì kéo các thể cho chạm nhau; bết thành cục thì tách cho có khe hở, hoặc thêm một
thể chìa ra ngoài để phá đường viền tròn.

**Cả BA danh sách CAN SUA phải rỗng** mới được báo xong: mối nối, bố cục, silhouette.

## Luật 4 — không đủ mảnh thì báo, không giao hàng xấu

Không có cụm phù hợp sau khi tra `parts` và nhìn sheet → nói thẳng thiếu gì, đã tìm
ở đâu, người dùng nên bổ sung FBX kiểu gì. Kết thúc bằng `RECIPE_NOT_POSSIBLE`.
Không giao model méo rồi im lặng. Không nói "xong" khi chưa nhìn ảnh preview.

## Luật 5 — file mới thả vào bất cứ lúc nào

Chạy `python meshforge/run.py sync` **đầu mỗi phiên**. Nó phát hiện file mới/đổi,
quét, đo hình học, tách cụm, render cụm, và gọi Claude đặt tên vào `parts.json`.
Sau đó file mới đã dùng được ngay. Mô tả cấp file (`files.json`) là phụ, cập nhật
sau qua `index_files.py`.

## Luật 6 — mảnh phù hợp hay nằm trong file có tên chẳng liên quan

Cái sừng đẹp nhất nằm trong `ToyBoxChapter07`. Khi cần một **hình dạng** chứ không
phải một **đồ vật**:

```bash
python meshforge/run.py find --shape cone --min 1.2 --sheet
python meshforge/run.py find --open --min 2.0 --mat Gold
```

`--shape`: `cone` `column` `hourglass` `bulge` `irregular`. Lọc thêm `--open`,
`--fill-min/max`, `--min/--max`, `--elong`, `--flat`, `--mat`, `--file`, `--exclude`.
Luôn kèm `--sheet` rồi đọc ảnh.

## Luật 7 — hai cụm kề nhau cùng material sẽ dính làm một khi nhìn

Kiểm `mats` của cụm kề nhau. Trùng thì ép một bên bằng `"material"` trong recipe.
Tương phản màu làm hình đọc được.

## Luật 8 — prompt gợi ý

`meshforge/designs.md` có 6 prompt mẫu đã viết chi tiết (bàn tiệc, giỏ hoa, nhân
vật lai, xe lai, cột đèn, quái vật). Khi được yêu cầu **tự nghĩ**, hãy dùng chúng làm
khuôn: nêu bộ khung → chốt 3–6 cụm → nói tỉ lệ bằng lời → cấm cụ thể → yêu cầu tương
phản màu. Không lặp lại ý đã có trong `recipes/`.

## Định dạng recipe

```json
{"name": "CatDrummer",
 "groups": [
  {"id": "base",  "cluster": "Vocalist#01", "anchor": "bottom_center", "pos": [0,0,0]},
  {"id": "body",  "cluster": "Vocalist#02", "drop": ["Vocalist/S_Vocalist_9"],
   "attach": {"to": "base", "at": "top", "snap": true}},
  {"id": "head",  "cluster": "Vocalist#06",
   "attach": {"to": "body", "at": "top", "snap": true, "contact": 0.6}},
  {"id": "drum",  "clusters": ["DrumChapter06#02"], "scale": 0.8,
   "attach": {"to": "base", "at": [0.75, 0.3, 1.0], "snap": true}}
 ],
 "parts": [
  {"id": "stick", "src": "DrumChapter06/S_Drum68", "scale": 0.9,
   "attach": {"to": "body", "at": "right", "snap": true}}
 ]}
```

- `attach.at`: `top` `bottom` `front` `back` `left` `right` `center` hoặc `[u,v,w]`
  toạ độ 0..1 trong hộp bao cha. Với `[u,v,w]`, `snap` chỉ kéo theo hướng ngắn nhất
  (không lún theo trục); muốn lún thêm thì dùng `bite`.
- `rest: true` — **tựa xuống bề mặt THẬT ngay bên dưới** (bắn tia xuống), thay vì bám
  đỉnh hộp bao. Bắt buộc khi đặt thứ gì **vào trong** vật lõm (chậu, khay có vành, giỏ):
  `snap` chỉ đưa tới *miệng* nên nhìn như treo lơ lửng. Nó tựa lên đúng thể mà nó
  `attach.to`, không tựa lên anh em cùng lứa.
- `anchor`: điểm gốc trên chính cụm này; mặc định suy từ `at`.
- `rot`: độ, Euler XYZ. Mảnh dài theo X muốn hất lên thì xoay quanh **Y**.
- `mirror: "x"` chỉ cho mesh lẻ, **không dùng trên cụm** (cụm là empty, sẽ crash).
- `material`: ép màu cho mesh lẻ **hoặc cả cụm** (áp lên mọi mesh bên trong).
- `place: "original"`: giữ toạ độ file gốc, chỉ để tham khảo bố cục.

## Rải nhiều bản — chống bố cục cứng nhắc

Ghép tay thì mọi thứ `rot = 0`, cách đều nhau, nhìn ra ngay là máy xếp. Dùng `scatter`:

```json
{"id": "petal", "cluster": "LotusPond#19", "scale": 1.8, "rest": true,
 "scatter": {"to": "pot", "at": "top", "count": 5,
             "angle": [0, 360], "radius": [0.55, 0.8], "tilt": [15, 35],
             "scale": [0.85, 1.15], "jitter": 0.1, "seed": 3}}
```

Sinh `petal_1..petal_5`, mỗi bản một góc toả, độ nghiêng ra ngoài và cỡ khác nhau.

| Khoá | Nghĩa |
|---|---|
| `count` | số bản |
| `angle` | cung toả; `[0,360]` là vòng kín chia đều |
| `radius` | **theo % nửa bề ngang thể cha** — `0.6` = 60% bán kính, không phụ thuộc scale |
| `tilt` | độ nghiêng ra ngoài (quay quanh Y) |
| `scale` | khoảng nhân thêm vào `scale` của nhóm |
| `jitter` | xê dịch góc ngẫu nhiên; 0.1 là đủ tự nhiên |
| `seed` | cố định để dựng lại ra y hệt |

**Chỉnh bằng bảng điểm, đừng mò:** `the bi vui` cao = các bản chen nhau → tăng `radius`
hoặc giảm `count`. `do dac` gần 0.93 = bết thành vành → tăng `tilt` cho xoè, hoặc giảm
`scale`.

## Bẫy đã gặp

- Hộp bao ≠ hình thật: 35% mesh có `fill` < 30%. Vì thế mới cần `snap`.
- `at: [u,v,1.0]` là mặt hộp bao, không phải mặt cong thật — snap sẽ kéo xuống.
- Nhiều file `Guitar_*` là đàn đã vỡ mảnh; chỉ `S_Guitar_13` còn nguyên.
- `Global_IceCream_fix` gần như rỗng. Nhiều cặp `X` / `X_Fix` là hai phiên bản.
- Không sửa `*.fbx` gốc. Kết quả ra `meshforge/out/`.
- `drop` (bỏ bớt mesh khỏi cụm) và `rest` (tựa xuống bề mặt) là **hai khoá khác nhau**.
- Mỗi lần `build` tự sao lưu recipe vào `recipes/_history/` (giữ 10 bản gần nhất).

## Khi được gọi từ nút trong Blender

Làm trọn quy trình, lặp tới khi bảng chấm điểm sạch và ảnh nhìn đúng, ghi recipe
đúng đường dẫn được giao, kết thúc bằng **một dòng duy nhất**:

- `RECIPE_READY: <tên>` — Blender tự dựng vào viewport.
- `RECIPE_NOT_POSSIBLE: <lý do ngắn>` — thư viện không đủ mảnh.
