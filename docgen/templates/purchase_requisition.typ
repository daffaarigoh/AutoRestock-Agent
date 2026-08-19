#let data = json("pr_payload.json")

#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2.2cm),
  header: align(right)[
    #text(8pt, fill: luma(120))[AutoRestock-Agent | Enterprise Automated Procurement System]
  ],
  footer: [
    #line(length: 100%, stroke: 0.5pt + luma(180))
    #grid(
      columns: (1fr, 1fr),
      text(8pt, fill: luma(100))[Generated autonomously by AI Multi-Agent System],
      align(right, text(8pt, fill: luma(100))[Page #counter(page).display()]),
    )
  ]
)
#set text(font: "Liberation Sans", size: 10pt)

// Header Perusahaan
#grid(
  columns: (1fr, 1fr),
  [
    #text(16pt, weight: "bold", fill: rgb("#1E3A8A"))[PURCHASE REQUISITION] \
    #text(9pt, fill: luma(100))[Nomor Dokumen: *#data.pr_number*] \
    #text(9pt, fill: luma(100))[Tanggal Terbit: #data.created_at]
  ],
  align(right)[
    #text(12pt, weight: "bold")[PT. WAREHOUSE NUSANTARA] \
    #text(8pt, fill: luma(120))[Divisi Otomasi Logistik & Pengadaan \ Jakarta, Indonesia]
  ]
)

#v(0.8em)
#line(length: 100%, stroke: 1.5pt + rgb("#1E3A8A"))
#v(0.5em)

// Ringkasan Alasan Pengadaan
#rect(fill: rgb("#F0FDF4"), stroke: rgb("#86EFAC"), radius: 4pt, width: 100%, inset: 10pt)[
  #text(weight: "bold", fill: rgb("#166534"))[Justifikasi Pengadaan Mandiri (qwen-35b):] \
  #text(size: 9pt)[Stok fisik beberapa SKU kritis berada di bawah safety threshold. Pemesanan dipercepat untuk mencegah bottleneck operasional gudang.]
]

#v(1em)
#text(11pt, weight: "bold")[Daftar Item Barang yang Dipesan:]

// Tabel Barang
#table(
  columns: (auto, 1.5fr, 1.2fr, auto, 1fr, 1fr),
  fill: (col, row) => if row == 0 { rgb("#1E3A8A") } else if calc.even(row) { rgb("#F8FAFC") } else { white },
  stroke: 0.5pt + luma(200),
  align: (center, left, left, center, right, right),
  
  table.header(
    text(fill: white, weight: "bold")[No],
    text(fill: white, weight: "bold")[Nama Barang],
    text(fill: white, weight: "bold")[Vendor Terpilih],
    text(fill: white, weight: "bold")[Qty],
    text(fill: white, weight: "bold")[Harga Satuan],
    text(fill: white, weight: "bold")[Total Biaya],
  ),
  
  ..data.items.enumerate().map(((i, item)) => (
    str(i + 1),
    item.name,
    item.vendor_name,
    str(item.reorder_qty) + " " + item.unit,
    "Rp " + str(item.unit_price),
    "Rp " + str(item.total_price),
  )).flatten()
)

#v(0.5em)
#align(right)[
  #text(12pt, weight: "bold")[Total Estimasi: #text(fill: rgb("#1E3A8A"))["Rp " + str(data.total_budget)]]
]

#v(1.2em)

// Catatan Compliance & Auditor dari Nemotron-35
#block(stroke: 0.8pt + rgb("#3B82F6"), fill: rgb("#EFF6FF"), inset: 9pt, radius: 4pt, width: 100%)[
  #text(weight: "bold", size: 9pt, fill: rgb("#1D4ED8"))[Hasil Audit Kepatuhan & Anggaran (nemotron-35):] \
  #text(size: 8.5pt, fill: luma(60))[Status: *#data.auditor_status* | #data.auditor_notes]
]

#v(2.5em)

// Kolom Approval Tanda Tangan
#grid(
  columns: (1fr, 1fr),
  align: center,
  [
    #text(9pt)[Dibuat Otomatis Oleh:] \
    #v(3.5em)
    #text(weight: "bold")[AutoRestock Multi-Agent] \
    #text(8pt, fill: luma(120))[System Autonomous Dispatch]
  ],
  [
    #text(9pt)[Persetujuan Manajer Pengadaan:] \
    #v(3.5em)
    #line(length: 65%, stroke: 0.8pt + luma(100))
    #text(weight: "bold")[Warehouse Manager] \
    #text(8pt, fill: luma(120))[Status Dokumen: *#data.status*]
  ]
)
