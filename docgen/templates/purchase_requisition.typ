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
