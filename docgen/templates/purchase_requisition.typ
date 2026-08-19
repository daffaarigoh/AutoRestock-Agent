// Purchase Requisition Typst Template
// AutoRestock-Agent Enterprise Document Engine

#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2.0cm, bottom: 2.0cm),
  header: align(right)[
    #text(size: 8.5pt, fill: rgb("#64748b"))[
      AutoRestock-Agent | Enterprise Autonomous Procurement System
    ]
  ],
  footer: align(center)[
    #text(size: 8.5pt, fill: rgb("#94a3b8"))[
      AutoRestock-Agent Requisition Document — Confirmed & Audited by AI Multi-Agent Engine
    ]
  ]
)

#set text(
  font: ("Segoe UI", "Roboto", "Liberation Sans", "Arial"),
  size: 9.5pt,
  fill: rgb("#1e293b")
)

#let doc_status = "{{STATUS}}"
#let status_color = if doc_status == "APPROVED" { rgb("#16a34a") } else if doc_status == "REJECTED" { rgb("#dc2626") } else { rgb("#d97706") }
#let status_bg = if doc_status == "APPROVED" { rgb("#f0fdf4") } else if doc_status == "REJECTED" { rgb("#fef2f2") } else { rgb("#fffbeb") }
#let status_border = if doc_status == "APPROVED" { rgb("#bbf7d0") } else if doc_status == "REJECTED" { rgb("#fecaca") } else { rgb("#fde68a") }

// Main Container
#block(width: 100%)[
  // Header section
  #grid(
    columns: (1fr, 1fr),
    align: (left, right),
    [
      #text(size: 16pt, weight: "bold", fill: rgb("#0f172a"))[PURCHASE REQUISITION]\
      #v(-2pt)
      #text(size: 10pt, weight: "medium", fill: rgb("#0284c7"))[AUTORESTOCK-AGENT ENTERPRISE]\
      #v(2pt)
      #text(size: 8.5pt, fill: rgb("#475569"))[
        Automated Smart Procurement & Safety Stock System\
        Warehouse & Supply Chain Division
      ]
    ],
    [
      #rect(
        stroke: status_border,
        radius: 6pt,
        fill: status_bg,
        inset: 10pt,
        [
          #text(size: 9pt, weight: "bold", fill: rgb("#334155"))[PR NUMBER:] #text(size: 9pt, weight: "bold", fill: rgb("#0f766e"))[{{PR_NUMBER}}]\
          #v(2pt)
          #text(size: 8.5pt, fill: rgb("#64748b"))[Date Created:] #text(size: 8.5pt, weight: "medium")[{{CREATED_AT}}]\
          #text(size: 8.5pt, fill: rgb("#64748b"))[Status:] #text(size: 9pt, weight: "bold", fill: status_color)[{{STATUS}}]
        ]
      )
    ]
  )

  #v(8pt)
  #line(length: 100%, stroke: 1.2pt + rgb("#0284c7"))
  #v(8pt)

  // Executive Summary Card
  #grid(
    columns: (1fr, 1fr, 1.2fr),
    gutter: 10pt,
    [
      #rect(
        width: 100%,
        stroke: rgb("#e2e8f0"),
        radius: 4pt,
        fill: rgb("#f1f5f9"),
        inset: 8pt,
        [
          #text(size: 8pt, fill: rgb("#64748b"), weight: "bold")[TOTAL ITEMS TO RESTOCK]\
          #v(2pt)
          #text(size: 12pt, weight: "bold", fill: rgb("#0f172a"))[{{TOTAL_ITEMS}} Items]
        ]
      )
    ],
    [
      #rect(
        width: 100%,
        stroke: rgb("#e2e8f0"),
        radius: 4pt,
        fill: rgb("#f1f5f9"),
        inset: 8pt,
        [
          #text(size: 8pt, fill: rgb("#64748b"), weight: "bold")[ESTIMATED TOTAL BUDGET]\
          #v(2pt)
          #text(size: 12pt, weight: "bold", fill: rgb("#0369a1"))[{{TOTAL_BUDGET}}]
        ]
      )
    ],
    [
      #rect(
        width: 100%,
        stroke: status_border,
        radius: 4pt,
        fill: status_bg,
        inset: 8pt,
        [
          #text(size: 8pt, fill: status_color, weight: "bold")[DECISION & AUDIT]\
          #v(2pt)
          #text(size: 11pt, weight: "bold", fill: status_color)[{{STATUS}} (#doc_status)]
        ]
      )
    ]
  )

  #v(10pt)
  #text(size: 11pt, weight: "bold", fill: rgb("#0f172a"))[Requisition Items Breakdown]
  #v(4pt)

  // Items Table
  #table(
    columns: (24pt, 62pt, 1fr, 45pt, 45pt, 85pt, 65pt, 75pt),
    align: (center, left, left, center, center, left, right, right),
    stroke: (x, y) => if y == 0 { (bottom: 1.5pt + rgb("#0284c7")) } else { (bottom: 0.5pt + rgb("#e2e8f0")) },
    fill: (x, y) => if y == 0 { rgb("#f8fafc") } else if calc.even(y) { rgb("#fafafa") } else { white },
    inset: (x: 4pt, y: 6pt),
    
    // Headers
    [*No*], [*Item ID*], [*Item Name & Justification*], [*Stock*], [*Reorder*], [*Vendor*], [*Unit Price*], [*Total Price*],
    
    // Rows injected by Python compiler
    {{ITEMS_TABLE_ROWS}}
  )

  #v(6pt)
  
  // Total Row Summary
  #align(right)[
    #block(width: 260pt)[
      #rect(stroke: rgb("#cbd5e1"), radius: 4pt, fill: rgb("#f8fafc"), inset: 8pt)[
        #grid(
          columns: (1fr, 1fr),
          align: (left, right),
          [#text(weight: "bold", size: 10pt)[Grand Total:]],
          [#text(weight: "bold", size: 11pt, fill: rgb("#0369a1"))[{{TOTAL_BUDGET}}]]
        )
      ]
    ]
  ]

  #v(6pt)

  // Auditor & Justification Note Box
  #rect(
    width: 100%,
    stroke: status_border,
    radius: 6pt,
    fill: status_bg,
    inset: 9pt,
    [
      #text(weight: "bold", size: 9pt, fill: status_color)[AI Auditor & Compliance Evaluation (Nemotron-35)]\
      #v(2pt)
      #text(size: 8.5pt, fill: rgb("#334155"))[{{AUDITOR_NOTES}}]
    ]
  )

  #v(12pt)

  // Signature / Authorization section
  #grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 15pt,
    align: center,
    [
      #text(size: 8.5pt, fill: rgb("#64748b"))[Prepared By:]\
      #v(30pt)
      #line(length: 80%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold")[Qwen-35b (AI Planner)]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[AutoRestock Workflow]
    ],
    [
      #text(size: 8.5pt, fill: rgb("#64748b"))[Audited & Checked By:]\
      #v(30pt)
      #line(length: 80%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold")[Nemotron-35 (AI Auditor)]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[Budget & Compliance]
    ],
    [
      #text(size: 8.5pt, fill: rgb("#64748b"))[Manager Decision:]\
      #v(30pt)
      #line(length: 80%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold", fill: status_color)[#doc_status]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[Human-In-The-Loop (HITL)]
    ]
  )
]
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
