#set page(
    paper: "a4",
    margin: (x: 2cm, y: 2cm),
    header: [
        #grid(
            columns: (1fr, 1fr),
            align(left)[#text(size: 8.5pt, fill: rgb("#64748b"))[DOKUMEN PENERIMAAN BARANG RESMI]],
            align(right)[#text(size: 8.5pt, fill: rgb("#64748b"))[No: DO/2026/08/8821]]
        )
        #line(length: 100%, stroke: 0.5pt + rgb("#e2e8f0"))
    ]
)
#set text(font: "Arial", size: 10pt, fill: rgb("#1e293b"))

#grid(
    columns: (2fr, 1fr),
    gutter: 10pt,
    [
        #text(size: 14pt, weight: "bold", fill: rgb("#0f172a"))[PT SUMBER ALFARIA DISTRIBUSI] \
        #text(size: 8.5pt, fill: rgb("#475569"))[
            Kawasan Industri MM2100 Blok B-12, Cikarang Barat \
            Bekasi, Jawa Barat 17530 | Telp: (021) 8983-4567 \
            Email: delivery\@alfaria-distribusi.co.id
        ]
    ],
    align(right)[
        #rect(
            fill: rgb("#f8fafc"),
            stroke: 1pt + rgb("#cbd5e1"),
            radius: 4pt,
            inset: 8pt
        )[
            #text(size: 10pt, weight: "bold", fill: rgb("#0f172a"))[FAKTUR SURAT JALAN] \
            #text(size: 8pt, fill: rgb("#64748b"))[(DELIVERY ORDER)] \
            #v(2pt)
            #text(size: 9.5pt, weight: "bold", fill: rgb("#0284c7"))[DO/2026/08/8821]
        ]
    ]
)

#v(8pt)
#line(length: 100%, stroke: 1.5pt + rgb("#0284c7"))
#v(6pt)

#grid(
    columns: (1fr, 1fr),
    gutter: 14pt,
    [
        #block(
            fill: rgb("#f8fafc"),
            inset: 8pt,
            radius: 4pt,
            stroke: 0.5pt + rgb("#e2e8f0"),
            width: 100%
        )[
            #text(weight: "bold", size: 8.5pt, fill: rgb("#475569"))[DETAIL PENGIRIM (SUPPLIER)] \
            #v(2pt)
            #text(weight: "bold", size: 10pt)[PT Sumber Alfaria Distribusi] \
            #text(size: 8.5pt, fill: rgb("#475569"))[Vendor ID: SUP-001] \
            #text(size: 8.5pt, fill: rgb("#475569"))[Driver: Budi Santoso (B 9876 TGR)]
        ]
    ],
    [
        #block(
            fill: rgb("#f8fafc"),
            inset: 8pt,
            radius: 4pt,
            stroke: 0.5pt + rgb("#e2e8f0"),
            width: 100%
        )[
            #text(weight: "bold", size: 8.5pt, fill: rgb("#475569"))[TUJUAN PENERIMAAN GUDANG] \
            #v(2pt)
            #text(weight: "bold", size: 10pt)[Gudang Sentral AutoRestock V2] \
            #text(size: 8.5pt, fill: rgb("#475569"))[Tanggal Masuk: 21 Agustus 2026] \
            #text(size: 8.5pt, fill: rgb("#475569"))[Status: Siap Sinkronisasi Stok Database]
        ]
    ]
)

#v(10pt)
#text(size: 11pt, weight: "bold", fill: rgb("#0f172a"))[DAFTAR BARANG MASUK / INPUT KATALOG:]
#v(4pt)

#table(
    columns: (25pt, 85pt, 1fr, 55pt, 75pt, 85pt),
    align: (center, left, left, center, right, right),
    stroke: (x, y) => if y == 0 { (bottom: 1.5pt + rgb("#0284c7")) } else { (bottom: 0.5pt + rgb("#e2e8f0")) },
    fill: (col, row) => if row == 0 { rgb("#f8fafc") } else { none },
    
    [#text(weight: "bold", size: 8.5pt)[No]],
    [#text(weight: "bold", size: 8.5pt)[Kode SKU]],
    [#text(weight: "bold", size: 8.5pt)[Nama Produk / Spesifikasi]],
    [#text(weight: "bold", size: 8.5pt)[Qty Masuk]],
    [#text(weight: "bold", size: 8.5pt)[Harga Satuan]],
    [#text(weight: "bold", size: 8.5pt)[Total Nilai]],

    [1], [FMCG-MINYAK-01], [Minyak Goreng Bimoli Klasik 2 Liter Pouch], [50 pouch], [Rp 36.500], [Rp 1.825.000],
    [2], [FMCG-INDOMIE-01], [Indomie Mi Instan Goreng Spesial (Karton 40 pcs)], [100 karton], [Rp 118.000], [Rp 11.800.000],
    [3], [FMCG-GULA-01], [Gula Pasir Gulaku Premium Tebu 1 Kg], [60 kg], [Rp 17.500], [Rp 1.050.000],
    [4], [FNB-KOPI-01], [Kopi Kapal Api Special Mix 20x25gr], [80 pack], [Rp 24.500], [Rp 1.960.000],
    [5], [OFC-KERTAS-01], [Kertas HVS PaperOne A4 80 GSM (Box 5 Rim)], [25 box], [Rp 245.000], [Rp 6.125.000],
)

#v(8pt)

#align(right)[
    #block(
        fill: rgb("#f8fafc"),
        inset: 10pt,
        radius: 4pt,
        stroke: 0.5pt + rgb("#cbd5e1"),
        width: 45%
    )[
        #grid(
            columns: (1fr, 1fr),
            align: (left, right),
            gutter: 4pt,
            [#text(size: 8.5pt)[Subtotal:]], [#text(size: 8.5pt, weight: "bold")[Rp 22.760.000]],
            [#text(size: 8.5pt)[PPN 11%:]], [#text(size: 8.5pt)[Rp 2.503.600]],
            [#line(length: 100%, stroke: 0.5pt + rgb("#94a3b8"))], [#line(length: 100%, stroke: 0.5pt + rgb("#94a3b8"))],
            [#text(weight: "bold", size: 10pt, fill: rgb("#0284c7"))[Grand Total Masuk:]], [#text(weight: "bold", size: 10pt, fill: rgb("#0284c7"))[Rp 25.263.600]]
        ]
    ]
]

#v(18pt)

#grid(
    columns: (1fr, 1fr, 1fr),
    align: center,
    [
        #text(size: 8.5pt)[Driver / Supplier],
        #v(35pt),
        #text(weight: "bold", size: 8.5pt)[( Budi Santoso )],
        #v(1pt),
        #text(size: 7.5pt, fill: rgb("#64748b"))[PT Sumber Alfaria]
    ],
    [
        #text(size: 8.5pt)[Pemeriksa / QC Gudang],
        #v(35pt),
        #text(weight: "bold", size: 8.5pt)[( Rahmat Hidayat )],
        #v(1pt),
        #text(size: 7.5pt, fill: rgb("#64748b"))[Staf Logistik]
    ],
    [
        #text(size: 8.5pt)[Kepala Gudang],
        #v(35pt),
        #text(weight: "bold", size: 8.5pt)[( Hendra Wijaya )],
        #v(1pt),
        #text(size: 7.5pt, fill: rgb("#64748b"))[Manager Gudang]
    ]
)
