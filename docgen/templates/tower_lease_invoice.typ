// Official Tower Lease Agreement & Tax Invoice Typst Template
// PT Bali Towerindo Sentra Tbk - Finance & Commercial Division
// Clean, corporate, professional document without emojis

#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 1.8cm, bottom: 1.8cm),
  header: align(right)[
    #text(size: 8pt, fill: rgb("#64748b"))[
      PT Bali Towerindo Sentra Tbk | Dokumen Resmi Keuangan & Komersial
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
          Dokumen Perjanjian Sewa & Tagihan diterbitkan otomatis melalui Enterprise Operations Portal.
        ]
      ],
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Halaman 1 dari 1 — Arsip Digital Finance Bali Tower
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
#let is_paid = doc_status == "PAID" or doc_status == "ACTIVE_PAID" or doc_status == "APPROVED"
#let status_color = if is_paid { rgb("#16a34a") } else { rgb("#d97706") }
#let status_bg = if is_paid { rgb("#f0fdf4") } else { rgb("#fffbeb") }
#let status_border = if is_paid { rgb("#bbf7d0") } else { rgb("#fde68a") }
#let display_status = if is_paid { "LUNAS (PAID)" } else { "MENUNGGU (PENDING)" }

// Header Kop Surat Perusahaan
#grid(
  columns: (1.2fr, 1fr),
  align: (left, right),
  [
    #text(size: 14pt, weight: "bold", fill: rgb("#0f172a"))[PT BALI TOWERINDO SENTRA TBK]\
    #v(-2pt)
    #text(size: 8.5pt, weight: "bold", fill: rgb("#2563eb"))[FINANCE & COMMERCIAL DIVISION - TOWER LEASING]\
    #v(2pt)
    #text(size: 7.5pt, fill: rgb("#64748b"))[
      Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4\
      Karet Kuningan, Setiabudi, Jakarta Selatan 12920, Indonesia\
      Telepon: (021) 522-8888 | Email: billing\@balitower.co.id
    ]
  ],
  [
    #text(size: 12pt, weight: "bold", fill: rgb("#0f172a"))[SURAT PERJANJIAN SEWA MENARA]\
    #text(size: 8.5pt, weight: "bold", fill: rgb("#475569"))[& INVOICE PENAGIHAN PERDANA]\
    #v(4pt)
    #rect(
      stroke: status_border,
      radius: 4pt,
      fill: status_bg,
      inset: (x: 8pt, y: 5pt),
      align(left)[
        #grid(
          columns: (85pt, 1fr),
          row-gutter: 2.5pt,
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[No. Invoice:]],
          [#text(size: 8pt, weight: "bold", fill: rgb("#1d4ed8"))[{{INVOICE_NUMBER}}]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[No. Kontrak MLA:]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#334155"))[{{CONTRACT_ID}}]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[Tgl Terbit:]],
          [#text(size: 7.5pt, weight: "medium")[{{INVOICE_DATE}}]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[Status Pembayaran:]],
          [#text(size: 7.5pt, weight: "bold", fill: status_color)[#display_status]]
        )
      ]
    )
  ]
)

#v(8pt)
#line(length: 100%, stroke: 1.2pt + rgb("#2563eb"))
#v(10pt)

// Section 1: Data Klien Operator (Penyewa)
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[1. IDENTITAS KLIEN OPERATOR (PENYEWA)]
#v(3pt)
#rect(
  stroke: 0.5pt + rgb("#cbd5e1"),
  radius: 4pt,
  fill: rgb("#f8fafc"),
  inset: 10pt,
  width: 100%,
  [
    #grid(
      columns: (110pt, 1fr, 110pt, 1fr),
      row-gutter: 6pt,
      [#text(weight: "bold", fill: rgb("#475569"))[Nama Perusahaan:]],
      [#text(weight: "bold", fill: rgb("#0f172a"))[{{CLIENT_NAME}}]],
      [#text(weight: "bold", fill: rgb("#475569"))[Kode Klien (ID):]],
      [#text(weight: "bold", fill: rgb("#1d4ed8"))[{{CLIENT_ID}}]],
      [#text(weight: "bold", fill: rgb("#475569"))[Tipe Entitas:]],
      [{{CLIENT_TYPE}}],
      [#text(weight: "bold", fill: rgb("#475569"))[NPWP Perusahaan:]],
      [{{NPWP}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Email Penagihan:]],
      [{{BILLING_EMAIL}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Syarat Pembayaran:]],
      [{{PAYMENT_TERMS}}]
    )
  ]
)

#v(10pt)

// Section 2: Spesifikasi Site Menara & Kontrak Sewa (MLA)
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[2. SPESIFIKASI SITE MENARA & MASA KONTRAK SEWA]
#v(3pt)
#rect(
  stroke: 0.5pt + rgb("#cbd5e1"),
  radius: 4pt,
  fill: rgb("#f8fafc"),
  inset: 10pt,
  width: 100%,
  [
    #grid(
      columns: (110pt, 1fr, 110pt, 1fr),
      row-gutter: 6pt,
      [#text(weight: "bold", fill: rgb("#475569"))[ID Site Menara:]],
      [#text(weight: "bold", fill: rgb("#0f172a"))[{{SITE_ID}}]],
      [#text(weight: "bold", fill: rgb("#475569"))[Nama Lokasi Site:]],
      [{{SITE_NAME}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Wilayah Operasional:]],
      [{{REGION}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Frekuensi Tagihan:]],
      [{{BILLING_FREQUENCY}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Masa Berlaku Kontrak:]],
      [{{START_DATE}} s/d {{END_DATE}} (5 Tahun)],
      [#text(weight: "bold", fill: rgb("#475569"))[Periode Tagihan:]],
      [{{PERIOD_COVERED}}]
    )
  ]
)

#v(10pt)

// Section 3: Rincian Finansial Tagihan
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[3. RINCIAN BIAYA & STRUKTUR TAGIHAN]
#v(3pt)
#table(
  columns: (30pt, 1fr, 80pt, 90pt, 100pt),
  stroke: 0.5pt + rgb("#e2e8f0"),
  fill: (col, row) => if row == 0 { rgb("#f1f5f9") } else { none },
  align: (center + horizon, left + horizon, center + horizon, right + horizon, right + horizon),
  inset: (x: 8pt, y: 7pt),
  [#text(weight: "bold", size: 8pt)[NO]],
  [#text(weight: "bold", size: 8pt)[DESKRIPSI LAYANAN SEWA]],
  [#text(weight: "bold", size: 8pt)[PERIODE]],
  [#text(weight: "bold", size: 8pt)[TARIF / BULAN]],
  [#text(weight: "bold", size: 8pt)[SUBTOTAL (IDR)]],

  [1],
  [
    *Sewa Ruang Antena & Shelter Menara Telekomunikasi*\
    #text(size: 7.5pt, fill: rgb("#64748b"))[Alokasi space menara mandiri, catu daya shelter, dan fasilitas backup site]
  ],
  [{{PERIOD_COVERED}}],
  [{{MONTHLY_RATE}}],
  [{{AMOUNT_SUBTOTAL}}]
)

#v(4pt)
#align(right)[
  #block(width: 280pt)[
    #grid(
      columns: (140pt, 1fr),
      row-gutter: 4pt,
      align: (left, right),
      [#text(size: 8.5pt, fill: rgb("#475569"))[Subtotal Biaya Sewa:]],
      [#text(size: 8.5pt, weight: "medium")[{{AMOUNT_SUBTOTAL}}]],
      [#text(size: 8.5pt, fill: rgb("#475569"))[PPN (11%):]],
      [#text(size: 8.5pt, weight: "medium")[{{TAX_PPN}}]],
      [#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))],
      [#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))],
      [#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[TOTAL TAGIHAN:]],
      [#text(size: 10.5pt, weight: "bold", fill: rgb("#1d4ed8"))[{{TOTAL_BILLED}}]],
      [#text(size: 8pt, fill: rgb("#475569"))[Batas Waktu Jatuh Tempo:]],
      [#text(size: 8pt, weight: "bold", fill: rgb("#dc2626"))[{{DUE_DATE}}]]
    )
  ]
]

#v(8pt)

// Section 4: Instruksi Pembayaran Bank
#rect(
  stroke: 0.5pt + rgb("#bfdbfe"),
  radius: 4pt,
  fill: rgb("#eff6ff"),
  inset: (x: 10pt, y: 8pt),
  width: 100%,
  [
    #text(weight: "bold", size: 8pt, fill: rgb("#1e40af"))[INFORMASI REKENING RESMI PEMBAYARAN PT BALI TOWERINDO SENTRA TBK:]\
    #v(2pt)
    #text(size: 7.5pt, fill: rgb("#1e3a8a"))[
      1. Bank Central Asia (BCA) KCU Sudirman | No. Rekening: *001-889-2231* a/n PT Bali Towerindo Sentra Tbk\
      2. Bank Mandiri KCP Rasuna Said | No. Rekening: *124-00-9988771-1* a/n PT Bali Towerindo Sentra Tbk\
      Cantumkan nomor invoice ({{INVOICE_NUMBER}}) pada berita transfer pembayaran.
    ]
  ]
)

#v(14pt)

// Section 5: Tanda Tangan & Otorisasi Resmi
#grid(
  columns: (1fr, 1fr),
  align: (center, center),
  [
    #text(size: 8pt, fill: rgb("#64748b"))[Disiapkan dan Divalidasi Oleh,]\
    #v(3pt)
    #text(weight: "bold", size: 8.5pt)[Billing & Commercial Specialist]\
    #v(32pt)
    #text(weight: "bold", size: 9pt)[TIMOTIUS ARYA, S.E.]\
    #text(size: 7.5pt, fill: rgb("#64748b"))[NIP: BLT-FIN-2019-042]
  ],
  [
    #text(size: 8pt, fill: rgb("#64748b"))[Disetujui dan Disahkan Oleh,]\
    #v(3pt)
    #text(weight: "bold", size: 8.5pt)[Direktur Keuangan & Komersial]\
    #v(32pt)
    #text(weight: "bold", size: 9pt)[HENDRA WIJAYA, M.M.]\
    #text(size: 7.5pt, fill: rgb("#64748b"))[Direksi PT Bali Towerindo Sentra Tbk]
  ]
)
