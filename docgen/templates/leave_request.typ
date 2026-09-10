// Official Employee Leave Request Typst Template
// PT Bali Towerindo Sentra Tbk - Human Resources & Field Operations Division

#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 1.8cm, bottom: 1.8cm),
  header: align(right)[
    #text(size: 8pt, fill: rgb("#64748b"))[
      PT Bali Towerindo Sentra Tbk | Dokumen Resmi Divisi Sumber Daya Manusia (HR)
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
          Dokumen Pengajuan Cuti Elektronik diterbitkan otomatis melalui Enterprise Operations Portal.
        ]
      ],
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Halaman 1 dari 1 — Arsip Digital HR Bali Tower
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

#let leave_status = "{{STATUS}}"
#let status_color = if leave_status == "APPROVED" { rgb("#16a34a") } else if leave_status == "REJECTED" { rgb("#dc2626") } else { rgb("#d97706") }
#let status_bg = if leave_status == "APPROVED" { rgb("#f0fdf4") } else if leave_status == "REJECTED" { rgb("#fef2f2") } else { rgb("#fffbeb") }
#let status_border = if leave_status == "APPROVED" { rgb("#bbf7d0") } else if leave_status == "REJECTED" { rgb("#fecaca") } else { rgb("#fde68a") }

// Header Kop Surat Perusahaan
#grid(
  columns: (1.2fr, 1fr),
  align: (left, right),
  [
    #text(size: 14pt, weight: "bold", fill: rgb("#0f172a"))[PT BALI TOWERINDO SENTRA TBK]\
    #v(-2pt)
    #text(size: 8.5pt, weight: "bold", fill: rgb("#0284c7"))[HUMAN RESOURCES & FIELD OPERATIONS DIVISION]\
    #v(2pt)
    #text(size: 7.5pt, fill: rgb("#64748b"))[
      Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4\
      Karet Kuningan, Setiabudi, Jakarta Selatan 12920, Indonesia\
      Telepon: (021) 522-8888 | Email: hr.operations\@balitower.co.id
    ]
  ],
  [
    #text(size: 13pt, weight: "bold", fill: rgb("#0f172a"))[SURAT PENGAJUAN CUTI]\
    #text(size: 8.5pt, weight: "bold", fill: rgb("#475569"))[FORMULIR PERMOHONAN RESMI]\
    #v(4pt)
    #rect(
      stroke: status_border,
      radius: 4pt,
      fill: status_bg,
      inset: (x: 8pt, y: 5pt),
      align(left)[
        #grid(
          columns: (80pt, 1fr),
          row-gutter: 2.5pt,
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[No. Pengajuan:]],
          [#text(size: 8pt, weight: "bold", fill: rgb("#0369a1"))[{{LEAVE_ID}}]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[Tgl Pengajuan:]],
          [#text(size: 7.5pt, weight: "medium")[{{SUBMIT_DATE}}]],
          [#text(size: 7.5pt, weight: "bold", fill: rgb("#475569"))[Status Dokumen:]],
          [#text(size: 7.5pt, weight: "bold", fill: status_color)[{{STATUS}}]]
        )
      ]
    )
  ]
)

#v(8pt)
#line(length: 100%, stroke: 1.2pt + rgb("#0284c7"))
#v(10pt)

// Section 1: Data Identitas Pemohon Cuti
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[1. IDENTITAS KARYAWAN PEMOHON]
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
      [#text(weight: "bold", fill: rgb("#475569"))[Nama Lengkap:]],
      [#text(weight: "bold", fill: rgb("#0f172a"))[{{EMPLOYEE_NAME}}]],
      [#text(weight: "bold", fill: rgb("#475569"))[NIK / ID Karyawan:]],
      [#text(weight: "bold", fill: rgb("#0369a1"))[{{EMPLOYEE_ID}}]],
      
      [#text(weight: "bold", fill: rgb("#475569"))[Posisi / Jabatan:]],
      [{{JOB_TITLE}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Departemen / Divisi:]],
      [{{DEPARTMENT}}],

      [#text(weight: "bold", fill: rgb("#475569"))[Sisa Kuota Cuti:]],
      [{{LEAVE_BALANCE}} Hari Kerja],
      [#text(weight: "bold", fill: rgb("#475569"))[Kontak Darurat:]],
      [{{PHONE}}]
    )
  ]
)

#v(8pt)

// Section 2: Rincian Permohonan Cuti
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[2. RINCIAN PERMOHONAN CUTI]
#v(3pt)
#rect(
  stroke: 0.5pt + rgb("#cbd5e1"),
  radius: 4pt,
  fill: rgb("#ffffff"),
  inset: 10pt,
  width: 100%,
  [
    #grid(
      columns: (110pt, 1fr),
      row-gutter: 6pt,
      [#text(weight: "bold", fill: rgb("#475569"))[Jenis Cuti:]],
      [#text(weight: "bold", fill: rgb("#0f172a"))[{{LEAVE_TYPE_LABEL}} ({{LEAVE_TYPE}})]],

      [#text(weight: "bold", fill: rgb("#475569"))[Periode Cuti:]],
      [{{START_DATE}} s/d {{END_DATE}}],

      [#text(weight: "bold", fill: rgb("#475569"))[Jumlah Hari Kerja:]],
      [#text(weight: "bold", fill: rgb("#0369a1"))[{{DAYS_REQUESTED}} Hari Kerja]],

      [#text(weight: "bold", fill: rgb("#475569"))[Alasan Pengajuan:]],
      [{{REASON}}]
    )
  ]
)

#v(8pt)

// Section 3: Personil Pengganti (Backup Staff)
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[3. PERSONIL PENGGANTI / BACKUP OPERASIONAL]
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
      [#text(weight: "bold", fill: rgb("#475569"))[Teknisi Pengganti:]],
      [#text(weight: "bold", fill: rgb("#0f172a"))[{{SUBSTITUTE_NAME}}]],
      [#text(weight: "bold", fill: rgb("#475569"))[ID Teknisi:]],
      [{{SUBSTITUTE_ID}}],

      [#text(weight: "bold", fill: rgb("#475569"))[Posisi / Keahlian:]],
      [{{SUBSTITUTE_TITLE}}],
      [#text(weight: "bold", fill: rgb("#475569"))[Serah Terima Tugas:]],
      [Telah dikoordinasikan secara operasional]
    )
  ]
)

#v(14pt)

// Section 4: Kolom Tanda Tangan & Persetujuan
#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[4. LEMBAR PENGESAHAN & PERSETUJUAN]
#v(5pt)

#grid(
  columns: (1fr, 1fr, 1fr),
  column-gutter: 12pt,
  [
    #align(center)[
      #text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Diajukan Oleh (Pemohon),]\
      #v(35pt)
      #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
      #text(weight: "bold", fill: rgb("#0f172a"))[{{EMPLOYEE_NAME}}]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[{{JOB_TITLE}}]
    ]
  ],
  [
    #align(center)[
      #text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Disetujui Pengganti,]\
      #v(35pt)
      #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
      #text(weight: "bold", fill: rgb("#0f172a"))[{{SUBSTITUTE_NAME}}]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[{{SUBSTITUTE_TITLE}}]
    ]
  ],
  [
    #align(center)[
      #text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Persetujuan Divisi HR,]\
      #v(35pt)
      #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
      #text(weight: "bold", fill: rgb("#0f172a"))[{{APPROVED_BY_NAME}}]\
      #text(size: 7.5pt, fill: rgb("#64748b"))[Human Resources Lead]
    ]
  ]
)

#v(12pt)
#align(center)[
  #text(size: 7.5pt, fill: rgb("#94a3b8"))[
    Surat pengajuan cuti ini sah dan dicatat dalam sistem manajemen kepegawaian PT Bali Towerindo Sentra Tbk secara digital.
  ]
]
