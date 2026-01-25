import streamlit as st
import os, shutil, json, hashlib, logging
from datetime import datetime
from validator import InsuranceValidator
import sqlite3

from security import initialize_security, sanitize_dict, mask_value  # uses your security.py

# -----------------------------
# Logging
# -----------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/audit.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -----------------------------
# Dirs
# -----------------------------
VALID_DIR = "validated_docs"
REVIEW_DIR = "review_needed"
INVALID_DIR = "invalid_docs"  # future manual rejection only
os.makedirs(VALID_DIR, exist_ok=True)
os.makedirs(REVIEW_DIR, exist_ok=True)
os.makedirs(INVALID_DIR, exist_ok=True)

# -----------------------------
# Security modules
# -----------------------------
sec = initialize_security()
audit_logger = sec["audit"]
fingerprints = sec["fingerprints"]

# -----------------------------
# Audit DB (NO sensitive fields)
# -----------------------------
def init_audit_db():
    conn = sqlite3.connect("audit_trail.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dossiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            file_name TEXT,
            file_hash TEXT,
            timestamp TEXT,
            score INTEGER,
            decision TEXT,
            fraud_suspected BOOLEAN,
            doc_type TEXT,
            reason_short TEXT
        )
    """)
    conn.commit()
    conn.close()

init_audit_db()

def compute_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def to_safe_reason(reason: str, max_len: int = 160) -> str:
    """
    Keep a short reason in DB (avoid storing PII).
    Long reason goes only to JSON report (sanitized).
    """
    r = (reason or "").replace("\n", " ").strip()
    if len(r) > max_len:
        r = r[:max_len] + "..."
    return r

def save_to_audit_db(case_id, file_name, file_hash, score, decision, fraud_suspected, doc_type, reason_short):
    conn = sqlite3.connect("audit_trail.db")
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""
        INSERT INTO dossiers (case_id, file_name, file_hash, timestamp, score, decision, fraud_suspected, doc_type, reason_short)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_id, file_name, file_hash, timestamp, int(score), decision, int(bool(fraud_suspected)), doc_type, reason_short))
    conn.commit()
    conn.close()

# -----------------------------
# Helpers
# -----------------------------
def safe_get_bank_fields(extracted: dict) -> tuple[str, str]:
    rib = (extracted.get("bank_rib") or "").strip()
    iban = (extracted.get("bank_iban") or "").strip()
    if not rib and not iban:
        legacy = (extracted.get("beneficiary_rib") or "").strip()
        if legacy.upper().startswith("MA"):
            iban = legacy
        else:
            rib = legacy
    return rib or "N/A", iban or "N/A"

def normalize_doc_type(doc_type: str) -> str:
    return (doc_type or "").strip().lower()

def docs_presence_summary(doc_results: list[dict]) -> dict:
    """
    Heuristic v2 (still simple):
    - death_certificate: doc_type contains deces/death
    - life_contract: doc_type contains assurance-vie/epargne/contract
    - id_present: doc_type contains cin/id/passport
    - bank: at least one doc extracted rib/iban
    """
    present = {
        "death_certificate": False,
        "life_contract": False,
        "id_present": False,
        "bank_rib_or_iban": False,
    }

    for r in doc_results:
        dt = normalize_doc_type(r.get("doc_type", ""))
        ex = r.get("extracted_data", {}) or {}
        rib, iban = safe_get_bank_fields(ex)

        if rib != "N/A" or iban != "N/A":
            present["bank_rib_or_iban"] = True

        if any(k in dt for k in ["deces", "décès", "death"]):
            present["death_certificate"] = True

        if any(k in dt for k in ["epargne", "épargne", "assurance-vie", "assurance vie", "life", "contract", "police"]):
            present["life_contract"] = True

        if any(k in dt for k in ["cin", "carte nationale", "id", "identity", "passport"]):
            present["id_present"] = True

    return present

def compute_case_decision(doc_results: list[dict]) -> tuple[str, str]:
    if not doc_results:
        return "REVIEW", "Aucun document analysé."

    any_review = any((r.get("decision") != "ACCEPT") for r in doc_results)
    any_fraud = any(bool(r.get("fraud_suspected")) for r in doc_results)

    presence = docs_presence_summary(doc_results)
    missing = [k for k, v in presence.items() if not v]

    if any_fraud:
        return "REVIEW", "Suspicion de fraude détectée (validation humaine obligatoire)."

    if missing:
        return "REVIEW", f"Documents obligatoires manquants (heuristique): {', '.join(missing)}"

    if any_review:
        return "REVIEW", "Au moins un document nécessite une vérification humaine."

    return "ACCEPT", "Tous les documents sont cohérents et complets (validation automatique)."

# -----------------------------
# Streamlit setup
# -----------------------------
st.set_page_config(page_title="Life Savings & Succession Validator", layout="wide", page_icon="🛡️")
st.title("🛡️ Life Savings & Succession Document Validator")
st.markdown("Traitement de dossiers épargne-vie / succession : extraction, cohérence, tri automatique.")
st.info("Règle: le système ne rejette jamais automatiquement. Toute suspicion (fraude/incohérence) => RÉVISION HUMAINE.")

@st.cache_resource
def get_validator():
    return InsuranceValidator()

validator = get_validator()

uploaded_files = st.file_uploader(
    "Déposez un dossier (PDF, PNG, JPG) — plusieurs fichiers possibles",
    accept_multiple_files=True,
    type=["pdf", "png", "jpg", "jpeg"]
)

if st.button("Lancer l'Audit IA (dossier)", type="primary"):
    if not uploaded_files:
        st.warning("Veuillez uploader au moins un document.")
        st.stop()

    case_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join("uploads_tmp", case_id)
    os.makedirs(temp_dir, exist_ok=True)

    doc_results = []

    for f in uploaded_files:
        if f.size > 50 * 1024 * 1024:
            st.error(f"❌ {f.name} dépasse 50MB → ignoré")
            logger.error(f"Fichier trop volumineux : {f.name}")
            continue

        local_path = os.path.join(temp_dir, f.name)
        with open(local_path, "wb") as tmp:
            tmp.write(f.getbuffer())

        try:
            # Dedup check (avoid paying Groq twice)
            is_dup, prev = fingerprints.is_duplicate(local_path)
            if is_dup:
                st.warning(f"⚠️ Doublon détecté: {f.name} (déjà vu: {prev}) → ignoré")
                continue

            file_hash = compute_file_hash(local_path)

            with st.spinner(f"Analyse : {f.name}"):
                text, struct, tech_report = validator.extract_all(local_path)
                result = validator.validate_with_groq(text, struct, tech_report)

            decision = result.get("decision", "REVIEW")
            score = int(result.get("score", 0) or 0)
            doc_type = result.get("doc_type", "UNKNOWN")
            fraud_suspected = bool(result.get("fraud_suspected", False))
            reason = result.get("reason", "Pas d'explication.")

            # Hard rule: tampering => REVIEW (never reject)
            if tech_report.get("potential_tampering"):
                fraud_suspected = True
                decision = "REVIEW"
                extra = f"Suspicion technique: {tech_report.get('editor_detected', 'éditeur inconnu')}"
                reason = (reason + " | " + extra).strip(" |")

            # Persist fingerprint after decision
            fingerprints.register_fingerprint(local_path, decision=decision, score=score)

            # Store for case
            result["decision"] = decision
            result["score"] = score
            result["doc_type"] = doc_type
            result["fraud_suspected"] = fraud_suspected
            result["reason"] = reason

            doc_results.append({
                "file_name": f.name,
                "file_hash": file_hash,
                "local_path": local_path,
                "result": result,
                "structure": struct,
                "tech_report": tech_report,
            })

            # Audit JSONL (sanitized)
            audit_logger.log_decision(
                case_id=case_id,
                file_name=f.name,
                file_hash=file_hash,
                score=score,
                decision=decision,
                fraud_suspected=fraud_suspected,
                doc_type=doc_type,
                extracted_fields=result.get("extracted_data", {}),
                reason=to_safe_reason(reason)
            )

            # Audit DB (short only)
            save_to_audit_db(
                case_id=case_id,
                file_name=f.name,
                file_hash=file_hash,
                score=score,
                decision=decision,
                fraud_suspected=fraud_suspected,
                doc_type=doc_type,
                reason_short=to_safe_reason(reason)
            )

        except Exception as e:
            st.error(f"❌ Erreur traitement {f.name} : {str(e)}")
            logger.error(f"Erreur traitement {f.name} : {str(e)}")

    if not doc_results:
        st.warning("Aucun document valide n'a été analysé.")
        st.stop()

    case_decision, case_reason = compute_case_decision([d["result"] for d in doc_results])

    # Save files per case
    dest_root = VALID_DIR if case_decision == "ACCEPT" else REVIEW_DIR
    case_dir = os.path.join(dest_root, case_id)
    os.makedirs(case_dir, exist_ok=True)

    for d in doc_results:
        shutil.copy(d["local_path"], os.path.join(case_dir, d["file_name"]))

    # Report.json (sanitized)
    report = {
        "case_id": case_id,
        "case_decision": case_decision,
        "case_reason": case_reason,
        "timestamp": datetime.now().isoformat(),
        "documents": []
    }

    for d in doc_results:
        r = d["result"]
        extracted = r.get("extracted_data", {}) or {}
        rib, iban = safe_get_bank_fields(extracted)

        report["documents"].append({
            "file_name": d["file_name"],
            "doc_type": r.get("doc_type", "UNKNOWN"),
            "decision": r.get("decision", "REVIEW"),
            "score": r.get("score", 0),
            "fraud_suspected": r.get("fraud_suspected", False),
            "reason_short": to_safe_reason(r.get("reason", "")),
            "extracted_preview": sanitize_dict({
                "insurer": extracted.get("insurer", "N/A"),
                "policy_number": extracted.get("policy_number", "N/A"),
                "beneficiary_name": extracted.get("beneficiary_name", "N/A"),
                "beneficiary_cin": extracted.get("beneficiary_cin", "N/A"),
                "bank_rib": rib,
                "bank_iban": iban,
                "amount": extracted.get("amount", "N/A")
            })
        })

    with open(os.path.join(case_dir, "report.json"), "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    # UI
    if case_decision == "ACCEPT":
        st.success(f"✅ DOSSIER ACCEPTÉ AUTOMATIQUEMENT — Case ID: {case_id}")
    else:
        st.warning(f"⚠️ DOSSIER EN RÉVISION HUMAINE — Case ID: {case_id}")
    st.caption(case_reason)

    st.divider()
    st.subheader("Résumé des documents")
    rows = []
    for d in doc_results:
        r = d["result"]
        extracted = r.get("extracted_data", {}) or {}
        rib, iban = safe_get_bank_fields(extracted)
        rows.append({
            "Fichier": d["file_name"],
            "Type": r.get("doc_type", "UNKNOWN"),
            "Décision": r.get("decision", "REVIEW"),
            "Score": r.get("score", 0),
            "Fraude suspectée": "✅" if r.get("fraud_suspected") else "—",
            "Bénéficiaire (nom)": extracted.get("beneficiary_name", "N/A"),
            "CIN (masqué)": mask_value(extracted.get("beneficiary_cin", "N/A"), keep_last=3),
            "RIB (masqué)": mask_value(re.sub(r"\\D", "", rib), keep_last=4) if rib != "N/A" else "N/A",
            "IBAN (masqué)": mask_value(iban, keep_last=4) if iban != "N/A" else "N/A",
        })
    st.dataframe(rows, use_container_width=True)

    st.divider()
    st.subheader("Détails")
    for d in doc_results:
        r = d["result"]
        with st.expander(f"📄 {d['file_name']} — {r.get('decision', 'REVIEW')} — score {r.get('score', 0)}", expanded=False):
            st.write(f"**Type:** {r.get('doc_type', 'UNKNOWN')}")
            st.write(f"**Fraude suspectée:** {'Oui' if r.get('fraud_suspected') else 'Non'}")
            st.write(f"**Raison (court):** {to_safe_reason(r.get('reason', ''))}")

            st.json(sanitize_dict({
                "extracted_data": r.get("extracted_data", {}),
                "dates_extracted": r.get("dates_extracted", {}),
                "format_validation": r.get("format_validation", {}),
                "tech_report": {
                    "metadata_suspecte": d["tech_report"].get("suspicious_metadata"),
                    "polices_detaillees": d["tech_report"].get("font_count"),
                    "fraude_potentielle": d["tech_report"].get("potential_tampering"),
                    "pages": d["structure"].get("page_count"),
                }
            }))

    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("📊 Tableau de bord")

def count_cases(base_dir: str) -> int:
    if not os.path.exists(base_dir):
        return 0
    return len([d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))])

st.sidebar.write(f"✅ **Dossiers acceptés :** {count_cases(VALID_DIR)}")
st.sidebar.write(f"⏳ **Dossiers en révision :** {count_cases(REVIEW_DIR)}")
st.sidebar.write(f"❌ **Rejetés (manuel) :** {len(os.listdir(INVALID_DIR)) if os.path.exists(INVALID_DIR) else 0}")

if st.sidebar.button("🗑️ Vider tous les dossiers (ACCEPT/REVIEW/INVALID)"):
    for d in [VALID_DIR, REVIEW_DIR, INVALID_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
    st.rerun()

if st.sidebar.button("📋 Voir audit trail (20 derniers)"):
    st.sidebar.subheader("Historique")
    conn = sqlite3.connect("audit_trail.db")
    c = conn.cursor()
    c.execute("""
        SELECT case_id, file_name, timestamp, score, decision, fraud_suspected
        FROM dossiers
        ORDER BY timestamp DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    conn.close()

    for row in rows:
        case_id, file_name, ts, score, decision, fraud = row
        st.sidebar.caption(f"{case_id} | {file_name} | {score}/100 | {decision} | fraude:{'Y' if fraud else 'N'}")
