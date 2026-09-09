// Official Purchase Requisition Typst Template
// PT Bali Towerindo Sentra Tbk - Enterprise Autonomous Procurement System

#set page(
  paper: "a4",
  margin: (x: 1.6cm, top: 1.6cm, bottom: 1.6cm),
  header: align(right)[
    #text(size: 8pt, fill: rgb("#64748b"))[
      PT Bali Towerindo Sentra Tbk | Official Enterprise Procurement Document
    ]
  ],
  footer: [
    #line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
    #v(3pt)
    #grid(
      columns: (1fr, 1fr),
      align: (left, right),
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Dokumen Purchase Requisition Resmi — PT Bali Towerindo Sentra Tbk (Audited by AI Multi-Agent Engine).
        ]
      ],
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Halaman 1 dari 1 — Arsip Digital Bali Tower
        ]
      ]
    )
  ]
)

#set text(
  font: ("Segoe UI", "Roboto", "Liberation Sans", "Arial"),
  size: 9pt,
  fill: rgb("#1e293b")
)

#let doc_status = "{{STATUS}}"
#let status_color = if doc_status == "APPROVED" { rgb("#16a34a") } else if doc_status == "REJECTED" { rgb("#dc2626") } else { rgb("#d97706") }
#let status_bg = if doc_status == "APPROVED" { rgb("#f0fdf4") } else if doc_status == "REJECTED" { rgb("#fef2f2") } else { rgb("#fffbeb") }
#let status_border = if doc_status == "APPROVED" { rgb("#bbf7d0") } else if doc_status == "REJECTED" { rgb("#fecaca") } else { rgb("#fde68a") }

// Main Container
#block(width: 100%)[
  // Header Kop Surat Perusahaan PT Bali Towerindo Sentra Tbk
  #grid(
    columns: (1.25fr, 1fr),
    align: (left, right),
    [
      #text(size: 15pt, weight: "bold", fill: rgb("#0f172a"))[PT BALI TOWERINDO SENTRA TBK]\
      #v(-2pt)
      #text(size: 9pt, weight: "semibold", fill: rgb("#0284c7"))[TELECOMMUNICATION INFRASTRUCTURE & FIBER OPTIC SOLUTIONS]\
      #v(2pt)
      #text(size: 8pt, fill: rgb("#64748b"))[
        Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4\
        Karet Kuningan, Setiabudi, Jakarta Selatan 12920, Indonesia\
        Telepon: (021) 522-8888 | Email: procurement\@balitower.co.id | www.balitower.co.id\
        #text(weight: "medium", fill: rgb("#334155"))[Divisi Logistik, Supply Chain & Pemeliharaan Infrastruktur Menara]
      ]
    ],
    [
      #text(size: 15pt, weight: "bold", fill: rgb("#0284c7"))[PURCHASE REQUISITION]\
      #text(size: 8.5pt, weight: "bold", fill: rgb("#475569"))[FORM PENGAJUAN PENGADAAN BARANG]\
      #v(3pt)
      #rect(
        stroke: status_border,
        radius: 4pt,
        fill: status_bg,
        inset: (x: 8pt, y: 6pt),
        align(left)[
          #grid(
            columns: (78pt, 1fr),
            row-gutter: 3pt,
            [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Nomor PR Resmi:]],
            [#text(size: 8.5pt, weight: "bold", fill: rgb("#0369a1"))[{{PR_NUMBER}}]],
            [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Tanggal Terbit:]],
            [#text(size: 8pt, weight: "medium")[{{CREATED_AT}}]],
            [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Status Dokumen:]],
            [#text(size: 8pt, weight: "bold", fill: status_color)[{{STATUS}}]]
          )
        ]
      )
    ]
  )

  #v(8pt)
  #line(length: 100%, stroke: 1.2pt + rgb("#0284c7"))
  #v(8pt)

  // Ringkasan Pengajuan (Executive Summary)
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
          #text(size: 8pt, fill: rgb("#64748b"), weight: "bold")[TOTAL ITEM REQUISITION]\
          #v(2pt)
          #text(size: 11pt, weight: "bold", fill: rgb("#0f172a"))[{{TOTAL_ITEMS}} Item Material]
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
          #text(size: 8pt, fill: rgb("#64748b"), weight: "bold")[ESTIMASI TOTAL ANGGARAN]\
          #v(2pt)
          #text(size: 11pt, weight: "bold", fill: rgb("#0369a1"))[{{TOTAL_BUDGET}}]
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
          #text(size: 8pt, fill: status_color, weight: "bold")[AUDIT & KELAYAKAN ANGGARAN]\
          #v(2pt)
          #text(size: 10pt, weight: "bold", fill: status_color)[
            #if doc_status == "APPROVED" [DISETUJUI (APPROVED)] else if doc_status == "REJECTED" [DITOLAK (REJECTED)] else [MENUNGGU PERSETUJUAN]
          ]
        ]
      )
    ]
  )

  #v(10pt)
  #text(size: 10.5pt, weight: "bold", fill: rgb("#0f172a"))[Rincian Kebutuhan Material & Justifikasi Restock]
  #v(4pt)

  // Items Table
  #table(
    columns: (22pt, 65pt, 1fr, 48pt, 48pt, 85pt, 65pt, 75pt),
    align: (center, left, left, center, center, left, right, right),
    stroke: (x, y) => if y == 0 { (bottom: 1.5pt + rgb("#0284c7")) } else { (bottom: 0.5pt + rgb("#e2e8f0")) },
    fill: (x, y) => if y == 0 { rgb("#f8fafc") } else if calc.even(y) { rgb("#fafafa") } else { white },
    inset: (x: 4pt, y: 6pt),
    
    // Headers
    [*No*], [*ID Material*], [*Deskripsi Material & Alasan Restock*], [*Stok*], [*Kebutuhan*], [*Supplier Rekanan*], [*Harga Satuan*], [*Subtotal*],
    
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
          [#text(weight: "bold", size: 9.5pt)[Total Anggaran PR:]],
          [#text(weight: "bold", size: 10.5pt, fill: rgb("#0369a1"))[{{TOTAL_BUDGET}}]]
        )
      ]
    ]
  ]

  #v(6pt)

  // Catatan Auditor AI & Justifikasi Kepatuhan
  #rect(
    width: 100%,
    stroke: status_border,
    radius: 5pt,
    fill: status_bg,
    inset: 8pt,
    [
      #text(weight: "bold", size: 8.5pt, fill: status_color)[Evaluasi Kepatuhan & Rekomendasi Audit Multi-Agent]\
      #v(2pt)
      #text(size: 8pt, fill: rgb("#334155"))[{{AUDITOR_NOTES}}]
    ]
  )

  #v(10pt)

  // Tanda Tangan & Pengesahan Dokumen
  #grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 15pt,
    align: center,
    [
      #text(size: 8pt, fill: rgb("#64748b"))[Diajukan Oleh (Prepared By):]\
      #v(28pt)
      #line(length: 85%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[Divisi Logistik & Gudang]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[PT Bali Towerindo Sentra Tbk]
    ],
    [
      #text(size: 8pt, fill: rgb("#64748b"))[Diverifikasi Oleh (Audited By):]\
      #v(28pt)
      #line(length: 85%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[AI Multi-Agent Auditor]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[Compliance & Budgeting System]
    ],
    [
      #text(size: 8pt, fill: rgb("#64748b"))[Persetujuan (Manager Approval):]\
      #v(28pt)
      #line(length: 85%, stroke: 0.8pt + rgb("#94a3b8"))
      #text(size: 8.5pt, weight: "bold", fill: status_color)[
        #if doc_status == "APPROVED" [DISETUJUI (APPROVED)] else if doc_status == "REJECTED" [DITOLAK (REJECTED)] else [PENDING APPROVAL]
      ]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[Head of Procurement & Supply Chain]
    ]
  )
]
