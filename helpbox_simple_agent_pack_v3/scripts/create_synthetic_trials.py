"""
Helper script to generate synthetic trial PDFs for Helpbox demo and testing.
Contains distinct, synthetic medical/protocol facts for Trial_101 and Trial_102.
"""
from pathlib import Path


def generate_pdf_bytes(title: str, body_text: str) -> bytes:
    escaped_body = body_text.replace("(", "\\(").replace(")", "\\)")
    escaped_title = title.replace("(", "\\(").replace(")", "\\)")
    
    stream_content = (
        "BT\n"
        "/F1 16 Tf\n"
        "50 720 Td\n"
        f"({escaped_title}) Tj\n"
        "/F1 11 Tf\n"
        "0 -30 Td\n"
        f"({escaped_body}) Tj\n"
        "ET\n"
    )
    stream_bytes = stream_content.encode("latin-1")
    obj4_body = f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1") + stream_bytes + b"endstream\n"
    
    parts = []
    parts.append(b"%PDF-1.4\n")
    offsets = [0]
    
    # obj 1: Catalog
    offsets.append(sum(len(p) for p in parts))
    parts.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    
    # obj 2: Pages
    offsets.append(sum(len(p) for p in parts))
    parts.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    
    # obj 3: Page
    offsets.append(sum(len(p) for p in parts))
    parts.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    
    # obj 4: Content stream
    offsets.append(sum(len(p) for p in parts))
    parts.append(b"4 0 obj\n" + obj4_body + b"endobj\n")
    
    # obj 5: Font
    offsets.append(sum(len(p) for p in parts))
    parts.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    
    # Xref & Trailer
    xref_offset = sum(len(p) for p in parts)
    xref = "xref\n0 6\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n"
    trailer = f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    parts.append(xref.encode("latin-1") + trailer.encode("latin-1"))
    
    return b"".join(parts)


def populate_synthetic_trials(trials_dir: Path):
    trials_dir.mkdir(parents=True, exist_ok=True)
    
    # Trial 101: Oncology study targeting Compound HB-101
    trial_101 = trials_dir / "Trial_101"
    trial_101.mkdir(exist_ok=True)
    
    p1 = trial_101 / "Protocol.pdf"
    if not p1.exists():
        p1.write_bytes(generate_pdf_bytes(
            "Trial 101 Protocol HB-101-ONC",
            "Primary Endpoint: Objective response rate at 24 weeks with oral HB-101 at 50mg daily."
        ))
        
    s1 = trial_101 / "Safety_Report.pdf"
    if not s1.exists():
        s1.write_bytes(generate_pdf_bytes(
            "Trial 101 Annual Safety Report",
            "Adverse Events: Grade 1 fatigue reported in 4 subjects; zero Grade 4 serious adverse events."
        ))

    # Trial 102: Cardiology study targeting Compound HB-202
    trial_102 = trials_dir / "Trial_102"
    trial_102.mkdir(exist_ok=True)
    
    p2 = trial_102 / "Protocol.pdf"
    if not p2.exists():
        p2.write_bytes(generate_pdf_bytes(
            "Trial 102 Protocol HB-202-CARD",
            "Primary Endpoint: Reduction in systolic blood pressure after 12 weeks with intravenous HB-202."
        ))
        
    c2 = trial_102 / "Clinical_Report.pdf"
    if not c2.exists():
        c2.write_bytes(generate_pdf_bytes(
            "Trial 102 Clinical Study Interim Report",
            "Efficacy Analysis: Mean reduction of 14.2 mmHg systolic pressure observed at week 12."
        ))


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent / "data" / "trials"
    populate_synthetic_trials(base)
    print(f"Synthetic trials populated in {base}")
