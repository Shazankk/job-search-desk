"""Build the fictional public sample resume with reproducible DOCX bytes."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from docx import Document
from docx.shared import Inches, Pt


OUTPUT = Path(__file__).resolve().parents[1] / "examples/sample-resume.docx"

INTRO = [
    "ASHA EXAMPLE",
    "HR Head | Strategic HR Business Partner | People Operations",
    "Pune, Maharashtra (Open to Remote)  |  +91 00000 00000  |  asha.example@example.com",
    "16 Years of Experience  |  IT Services, Technology & Insurance (BFSI)  |  Executive Programme in HR Management",
    "PROFESSIONAL SUMMARY",
    "HR leader with 16 years across IT services, software technology and insurance. Connects people strategy with dependable HR operations, payroll, performance management and compensation & benefits. Leads talent acquisition, learning & development, organisation development and employee engagement, supported by statutory compliance, M&A integration, HR analytics and HRMS digitisation.",
    "KEY ACHIEVEMENTS",
    "Workplace certification: Coordinated an internal workplace-certification programme using staff feedback and documented improvements to manager practices.",
    "Culture award: Established a peer-nominated culture award that recognised inclusive teamwork across distributed teams.",
    "People integration: Aligned onboarding, policies and compensation review schedules during an M&A integration without interrupting payroll.",
    "HR digitisation: Introduced an HRMS and monthly dashboards to replace disconnected leave, attendance and appraisal trackers.",
    "Leadership development: Built a practical L&D series where new managers rehearsed feedback conversations and team planning.",
    "CORE COMPETENCIES",
    "Strategic HR & Business Partnering (HRBP)  •  HR Operations, Policies & SOPs  •  Performance Management (KRAs, KPIs, Competency Framework)  •  Talent Acquisition & Workforce Planning  •  Compensation, Benefits & Rewards  •  Learning & Development  •  Organisation Development & Change Management  •  Employee Engagement & Experience  •  Employee Relations  •  Employer Branding (LinkedIn, AmbitionBox)  •  HR Analytics & Dashboards  •  Statutory Compliance, Labour Law & POSH  •  M&A Integration  •  Diversity, Equity & Inclusion",
    "HRMS / HR Tech: Keka, Zoho People, greytHR; exposure to SAP and Darwinbox; AI-based recruitment tools",
    "PROFESSIONAL EXPERIENCE",
]

ROLES = [
    (
        "HR Head\tJan 2023 – Present",
        "Fictional Northwind Software Pvt Ltd, Pune",
        [
            "Set the people strategy for software delivery teams and translated staffing priorities into quarterly workforce plans.",
            "Led compensation reviews with clear role bands and documented decisions on benefits and rewards.",
            "Implemented Keka HRIS workflows for leave, attendance and payroll checks, with HR dashboards for leadership reviews.",
            "Guided M&A people integration through policy mapping, manager briefings and change management workshops.",
            "Reviewed statutory compliance and POSH training completion with an established internal committee.",
        ],
    ),
    (
        "Senior HR Manager\tJul 2019 – Dec 2022",
        "Fictional Bluepeak Technologies Pvt Ltd, Pune",
        [
            "Rebuilt performance management around agreed KRAs, KPIs and a competency framework for technical and support roles.",
            "Managed talent acquisition from hiring plans through structured interviews and onboarding check-ins.",
            "Introduced Zoho People records and self-service requests while reconciling employee data before migration.",
            "Organised learning & development sessions and employee engagement circles using feedback from project teams.",
            "Published HR policies and SOPs that clarified approvals, employee relations processes and manager responsibilities.",
        ],
    ),
    (
        "HR Business Partner\tApr 2016 – Jun 2019",
        "Fictional Harbourline Insurance Ltd, Mumbai",
        [
            "Partnered with insurance operations leaders on staffing, succession discussions and people risks across service teams.",
            "Coordinated appraisals and compensation reviews with consistent evidence requirements for managers.",
            "Delivered POSH awareness workshops and tracked statutory compliance actions with the HR operations team.",
            "Supported organisation development during a branch restructuring through role consultations and manager coaching.",
        ],
    ),
    (
        "HR Manager\tJan 2013 – Mar 2016",
        "Fictional Willowquay IT Services Pvt Ltd, Pune",
        [
            "Owned monthly payroll inputs, attendance reconciliation and benefit enrolment checks for IT services staff.",
            "Planned recruitment campaigns with delivery managers and maintained a shared view of vacancies and joining dates.",
            "Launched a learning calendar covering communication, supervisory skills and employee relations responsibilities.",
            "Used greytHR reports to monitor headcount movements and resolve discrepancies before management reporting.",
        ],
    ),
    (
        "HR Executive\tJan 2010 – Dec 2012",
        "Fictional Copperkite Business Systems Pvt Ltd, Pune",
        [
            "Prepared joining records, induction schedules and payroll change registers with documented review steps.",
            "Scheduled recruitment interviews and maintained candidate updates through offer and onboarding stages.",
            "Supported annual appraisals by collecting review forms and following up on incomplete manager feedback.",
            "Coordinated staff engagement activities and maintained accessible records of HR policies and training attendance.",
        ],
    ),
]

ENDING = [
    "EDUCATION",
    "Executive Programme in HR Management, Fictional Meadowbridge Institute of Management, 2018",
    "Bachelor of Business Administration, Fictional Lanternvale College, 2009",
    "CERTIFICATIONS",
    "Internal HR Analytics Workshop Certificate; Workplace Facilitation Practice Certificate; POSH Awareness Training",
    "Languages: English, Hindi, Marathi",
]


def main():
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(5)
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Inches(0.6)
        section.left_margin = section.right_margin = Inches(0.7)
    headings = {
        "PROFESSIONAL SUMMARY", "KEY ACHIEVEMENTS", "CORE COMPETENCIES",
        "PROFESSIONAL EXPERIENCE", "EDUCATION", "CERTIFICATIONS",
    }

    def add(text, bullet=False):
        paragraph = doc.add_paragraph(text, style="List Bullet" if bullet else "Normal")
        if text == "ASHA EXAMPLE" or text in headings:
            paragraph.runs[0].bold = True

    for text in INTRO:
        add(text)
    for title, employer, bullets in ROLES:
        add(title)
        add(employer)
        for text in bullets:
            add(text, bullet=True)
    for text in ENDING:
        add(text)

    props = doc.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.title = "ASHA EXAMPLE — Fictional Sample Resume"
    props.subject = "Fictional demonstration data"
    props.comments = ""
    props.created = props.modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    props.revision = 1
    buffer = BytesIO()
    doc.save(buffer)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # ZIP timestamps otherwise depend on the time the generator is run.
    with ZipFile(buffer) as source, ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            target.writestr(info, source.read(name))
    print(OUTPUT)


if __name__ == "__main__":
    main()
