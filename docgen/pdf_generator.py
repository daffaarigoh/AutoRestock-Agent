"""
Enterprise Document Generator (Typst-based)
Compiles official, high-resolution Purchase Requisition (Surat Permintaan Pembelian) PDFs.
"""

from pathlib import Path
import typst
from typing import Optional
from datetime import datetime
from core.config import settings
from core.schemas import PurchaseRequisition
from core.observability import log_agent_step


class PDFGenerator:
    def __init__(self):
        self.output_dir = settings.STORAGE_DIR / "documents"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_pr_pdf(self, pr: PurchaseRequisition) -> str:
        """
        Renders a Purchase Requisition into an official PDF document using Typst.
        Returns the absolute path to the generated PDF.
        """
        log_agent_step(
            step_name="PR PDF Compilation",
            agent_name="DocGenEngine",
            status="running",
            message=f"Compiling official PDF for Purchase Requisition {pr.pr_number}..."
        )

        base_name = pr.pr_number.replace('/', '_')
        output_typ_path = self.output_dir / f"{base_name}.typ"
        output_pdf_path = self.output_dir / f"{base_name}.pdf"

        # Format currency helper
        def fmt_curr(val: float) -> str:
            return f"Rp {val:,.0f}".replace(",", ".")

        # Build items table rows in Typst syntax
        items_markup = ""
        for idx, item in enumerate(pr.items):
            items_markup += f"""
            [{idx + 1}],
            [{item.sku}],
            [{item.item_name}],
            [{item.quantity} {item.unit}],
            [{fmt_curr(item.unit_price)}],
            [{fmt_curr(item.total_price)}],
            """

        status_color = "rgb(\"#16a34a\")" if pr.status == "approved" else "rgb(\"#d97706\")"
        if pr.status == "rejected":
            status_color = "rgb(\"#dc2626\")"

        typst_source = f"""
#set page(
    paper: "a4",
    margin: (x: 2cm, y: 2cm),
    header: [
        #grid(
            columns: (1fr, 1fr),
            align(left)[#text(size: 8pt, fill: rgb("#64748b"))[AUTORESTOCK-V2 ENTERPRISE PROCUREMENT SYSTEM]],
            align(right)[#text(size: 8pt, fill: rgb("#64748b"))[Official Document]]
        )
        #line(length: 100%, stroke: 0.5pt + rgb("#e2e8f0"))
    ]
)
#set text(font: "Arial", size: 10pt, fill: rgb("#1e293b"))

// Header Section
#grid(
    columns: (2fr, 1fr),
    gutter: 10pt,
    [
        #text(size: 15pt, weight: "bold", fill: rgb("#0f172a"))[PT RETAIL LOGISTIK NUSANTARA] \\
        #text(size: 8.5pt, fill: rgb("#475569"))[
            Gedung Logistik Sentral Lt. 4, Kawasan Industri Pulogadung \\
            Jakarta Timur, DKI Jakarta 13920 | Telp: (021) 460-9988 \\
            Email: procurement\\@retail-nusantara.co.id
        ]
    ],
    align(right)[
        #rect(
            fill: rgb("#f8fafc"),
            stroke: 1pt + rgb("#cbd5e1"),
            radius: 4pt,
            inset: 8pt
        )[
            #text(size: 10pt, weight: "bold", fill: rgb("#0f172a"))[SURAT PERMINTAAN PEMBELIAN] \\
            #text(size: 8pt, fill: rgb("#64748b"))[(PURCHASE REQUISITION)] \\
            #v(2pt)
            #text(size: 9.5pt, weight: "bold", fill: rgb("#2563eb"))[{pr.pr_number}]
        ]
    ]
)

#v(8pt)
#line(length: 100%, stroke: 1.5pt + rgb("#0f172a"))
#v(6pt)

// Information Grid
#grid(
    columns: (1fr, 1fr),
    gutter: 14pt,
    [
        #block(
            fill: rgb("#f8fafc"),
            inset: 8pt,
            radius: 4pt,
            stroke: 0.5pt + rgb("#e2e8f0")
        )[
            #text(weight: "bold", size: 9pt)[INFORMASI DOKUMEN:] \\
            #grid(
                columns: (85pt, 1fr),
                gutter: 4pt,
                [Tanggal Terbit:], [{pr.created_at}],
                [Prioritas / Urgensi:], [#text(weight: "bold", fill: rgb("#b45309"))[{pr.urgency}]],
                [Status Dokumen:], [#text(weight: "bold", fill: {status_color})[{pr.status.upper() if isinstance(pr.status, str) else pr.status.value.upper()}]],
                [Otorisasi Sistem:], [Auto-Restock Agent V2]
            )
        ]
    ],
    [
        #block(
            fill: rgb("#f8fafc"),
            inset: 8pt,
            radius: 4pt,
            stroke: 0.5pt + rgb("#e2e8f0")
        )[
            #text(weight: "bold", size: 9pt)[TARGET SUPPLIER / VENDOR:] \\
            #grid(
                columns: (80pt, 1fr),
                gutter: 4pt,
                [ID Vendor:], [{pr.supplier_id}],
                [Nama Vendor:], [#text(weight: "bold")[{pr.supplier_name}]],
                [Alamat Kirim:], [Gudang Utama - Loading Dock 2],
                [Metode Bayar:], [Net 30 Days]
            )
        ]
    ]
)

#v(10pt)
#text(weight: "bold", size: 10pt)[RINCIAN BARANG / MATERIAL YANG DIPESAN:]
#v(4pt)

// Items Table
#table(
    columns: (24pt, 85pt, 1fr, 55pt, 75pt, 85pt),
    fill: (col, row) => if row == 0 {{ rgb("#f1f5f9") }} else if calc.even(row) {{ rgb("#f8fafc") }} else {{ rgb("#ffffff") }},
    stroke: 0.5pt + rgb("#cbd5e1"),
    inset: (x: 6pt, y: 6pt),
    align: (col, row) => (
        if row == 0 {{ center + horizon }}
        else if col == 0 {{ center + horizon }}
        else if col == 3 or col == 4 or col == 5 {{ right + horizon }}
        else {{ left + horizon }}
    ),
    [*No*], [*SKU*], [*Deskripsi Item*], [*Jumlah*], [*Harga Satuan*], [*Total Harga*],
    {items_markup}
)

#v(6pt)

// Financial Summary
#align(right)[
    #block(width: 250pt)[
        #table(
            columns: (120pt, 1fr),
            stroke: none,
            inset: 3pt,
            align: (left, right),
            [Subtotal Rincian:], [{fmt_curr(pr.subtotal)}],
            [PPN 11% (Pajak Masukan):], [{fmt_curr(pr.tax_amount)}],
            [#line(length: 100%, stroke: 0.5pt + rgb("#94a3b8"))], [#line(length: 100%, stroke: 0.5pt + rgb("#94a3b8"))],
            [#text(weight: "bold", size: 10.5pt)[TOTAL ESTIMASI:]], [#text(weight: "bold", size: 10.5pt, fill: rgb("#0f172a"))[{fmt_curr(pr.grand_total)}]]
        )
    ]
]

#v(8pt)

// Notes
#if "{pr.notes or ''}" != "" [
    #block(
        fill: rgb("#fffbeb"),
        inset: 7pt,
        radius: 4pt,
        stroke: 0.5pt + rgb("#fde68a")
    )[
        #text(weight: "bold", size: 8.5pt, fill: rgb("#92400e"))[Catatan / Instruksi Pengadaan:] \\
        #text(size: 8pt, fill: rgb("#78350f"))[{pr.notes}]
    ]
]

#v(16pt)

// Signatures Block
#grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 15pt,
    align: center,
    [
        #text(size: 8pt)[Dibuat Otomatis Oleh:] \\
        #v(30pt)
        #text(weight: "bold", size: 8.5pt)[AutoRestock AI Agent] \\
        #text(size: 7.5pt, fill: rgb("#64748b"))[Autonomous Inventory Engine]
    ],
    [
        #text(size: 8pt)[Diperiksa Oleh:] \\
        #v(30pt)
        #text(weight: "bold", size: 8.5pt)[Koordinator Gudang] \\
        #text(size: 7.5pt, fill: rgb("#64748b"))[Warehouse Operations]
    ],
    [
        #text(size: 8pt)[Disetujui Oleh:] \\
        #v(30pt)
        #text(weight: "bold", size: 8.5pt)[{pr.approver_name or 'Manager Pengadaan'}] \\
        #text(size: 7.5pt, fill: rgb("#64748b"))[Procurement Dept.]
    ]
)
"""

        try:
            # Write .typ file first
            with open(output_typ_path, "w", encoding="utf-8") as f:
                f.write(typst_source)

            # Compile .typ to .pdf
            typst.compile(str(output_typ_path), output=str(output_pdf_path))

            log_agent_step(
                step_name="PR PDF Compilation",
                agent_name="DocGenEngine",
                status="success",
                message=f"Purchase Requisition PDF successfully generated: {output_pdf_path.name}",
                details={"file_path": str(output_pdf_path), "size_bytes": output_pdf_path.stat().st_size}
            )
        except Exception as e:
            log_agent_step(
                step_name="PR PDF Compilation",
                agent_name="DocGenEngine",
                status="error",
                message=f"Typst compilation encountered an issue: {str(e)}"
            )
            # In case of font or system issue, record None
            return ""

        return str(output_pdf_path)


pdf_generator = PDFGenerator()
