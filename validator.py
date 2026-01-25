import os
import fitz  # PyMuPDF
import easyocr
import json
import groq
from groq import Groq
from dotenv import load_dotenv

from utils import (
    validate_iban,
    validate_cin_morocco,
    validate_dates_coherence,
)

load_dotenv()


class InsuranceValidator:
    """
    Validator OCR + extraction + checks.
    IMPORTANT POLICY:
    - The AI NEVER makes a final REJECT decision.
    - It only returns: decision = "ACCEPT" or "REVIEW"
    - Even if fraud is suspected => decision MUST be "REVIEW" (human decides).
    """

    def __init__(self):
        # OCR: French + English (add 'ar' if you need Arabic later)
        self.reader = easyocr.Reader(["fr", "en"])

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY non trouvée ! Vérifiez votre fichier .env.")
        self.client = Groq(api_key=api_key)
        self.groq_timeout = 30  # seconds

    # -----------------------------
    # Fraud / Integrity (PDF level)
    # -----------------------------
    def analyze_technical_integrity(self, doc, file_path: str) -> dict:
        """Detect suspicious metadata/editors and font anomalies (signals only, not final reject)."""
        metadata = doc.metadata or {}

        fraud_tools = ["canva", "photoshop", "illustrator", "gimp", "inkscape", "adobe acrobat pro"]
        creator = (metadata.get("creator") or "").lower()
        producer = (metadata.get("producer") or "").lower()
        is_suspicious_tool = any(tool in creator or tool in producer for tool in fraud_tools)

        fonts = []
        for page in doc:
            fonts.extend([f[3] for f in page.get_fonts()])
        unique_fonts = set(fonts)

        # Heuristic: font variety can be a signal, not a verdict
        font_count = len(unique_fonts)
        potential_tampering = bool(is_suspicious_tool or font_count > 8)

        return {
            "suspicious_metadata": bool(is_suspicious_tool),
            "editor_detected": creator if creator else producer,
            "font_count": font_count,
            "potential_tampering": potential_tampering,
            "file_path": file_path,
        }

    # -----------------------------
    # OCR & Structure extraction
    # -----------------------------
    def extract_all(self, file_path: str):
        """Extract OCR text + structure + technical integrity report."""
        text_results = []
        structure = {"has_images": False, "page_count": 0, "has_tables": False}

        doc = fitz.open(file_path)
        structure["page_count"] = len(doc)

        tech_report = self.analyze_technical_integrity(doc, file_path)

        for page in doc:
            if len(page.get_images()) > 0:
                structure["has_images"] = True
            if len(page.get_drawings()) > 10:
                structure["has_tables"] = True

            pix = page.get_pixmap()
            # easyocr expects image bytes
            text_results.extend(self.reader.readtext(pix.tobytes("png"), detail=0))

        return " ".join(text_results), structure, tech_report

    # -----------------------------
    # LLM extraction + validation
    # -----------------------------
    def validate_with_groq(self, text: str, structure: dict, tech_report: dict) -> dict:
        """
        Extract fields and propose a decision:
        - "ACCEPT" only if everything is complete + coherent + no fraud signals
        - otherwise "REVIEW"
        NOTE: AI never final-rejects.
        """
        prompt = f"""
RÔLE : Auditeur Assurance (Contexte MAROC) - Dossiers épargne-vie / succession.

DONNÉES TECHNIQUES (SIGNAL UNIQUEMENT) :
- Structure : {structure}
- Suspicion technique : {tech_report.get('potential_tampering')} (éditeur : {tech_report.get('editor_detected')})
- Nombre de polices distinctes : {tech_report.get('font_count')}

TEXTE OCR (extrait) :
{text[:4000]}

MISSION :
1) Identifier le type de document (ou document probable).
2) Extraire les champs utiles (bénéficiaire, contrat, banque, dates).
3) Proposer une décision : "ACCEPT" ou "REVIEW".
IMPORTANT : Tu ne rejettes JAMAIS définitivement. Si doute ou suspicion => "REVIEW".

INDICATIONS MAROC :
- IBAN Maroc commence souvent par "MA" (ex: MA + 24-26 caractères après selon format affiché).
- RIB peut apparaître en groupes de chiffres (format d'affichage variable).
- CIN Maroc : format alphanumérique (variable). Si tu n'es pas sûr, remplis quand même mais indique l'incertitude dans reason.

CHAMPS À EXTRAIRE (si présents) :
- insurer, policy_number
- deceased_name (si le document contient le défunt)
- beneficiary_name, beneficiary_cin
- bank_rib (si présent), bank_iban (si présent)
- start_date, end_date (si document a une période)
- amount (si présent)

RÈGLES DÉCISION :
- "ACCEPT" seulement si : champs critiques présents + formats OK + cohérences internes OK + AUCUNE suspicion fraude.
- Si métadonnées/édition suspectes OU champs manquants OU incohérences => "REVIEW".

Réponds UNIQUEMENT en JSON :
{{
  "decision": "ACCEPT" | "REVIEW",
  "score": 0,
  "country": "MAROC",
  "doc_type": "",

  "fraud_suspected": false,
  "fraud_signals": [],

  "dates_extracted": {{
    "start_date": "",
    "end_date": "",
    "dates_coherent": true
  }},

  "extracted_data": {{
    "insurer": "",
    "policy_number": "",
    "deceased_name": "",
    "beneficiary_name": "",
    "beneficiary_cin": "",
    "bank_rib": "",
    "bank_iban": "",
    "amount": ""
  }},

  "format_validation": {{
    "dates_format_valid": true,
    "rib_format_valid": true,
    "iban_format_valid": true,
    "cin_format_valid": true
  }},

  "reason": ""
}}
""".strip()

        try:
            chat = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                timeout=self.groq_timeout,
                response_format={"type": "json_object"},
            )
            result = json.loads(chat.choices[0].message.content)
            return self._validate_extracted_data(result, tech_report=tech_report)

        except groq.AuthenticationError:
            raise ValueError("Clé API GROQ invalide.")
        except Exception as e:
            # Never reject: system error => REVIEW
            return {
                "decision": "REVIEW",
                "is_valid": False,
                "score": 0,
                "country": "MAROC",
                "doc_type": "UNKNOWN",
                "fraud_suspected": False,
                "fraud_signals": [],
                "dates_extracted": {"start_date": "", "end_date": "", "dates_coherent": False},
                "extracted_data": {},
                "format_validation": {},
                "reason": f"Erreur API/système : {str(e)}",
            }

    # -----------------------------
    # Post validation (no auto-reject)
    # -----------------------------
    def _validate_extracted_data(self, groq_result: dict, tech_report: dict | None = None) -> dict:
        """
        Post-traitement :
        - Validate CIN
        - Validate dates coherence (if both exist)
        - Validate IBAN (if present)
        - Validate RIB (if validate_rib_morocco exists; otherwise only checks presence)
        - Add fraud signals from tech_report
        POLICY: decision is only ACCEPT or REVIEW (never final REJECT).
        """
        tech_report = tech_report or {}
        format_errors = []
        fraud_signals = []

        # Ensure keys exist
        groq_result = groq_result or {}
        groq_result.setdefault("format_validation", {})
        groq_result.setdefault("extracted_data", {})
        groq_result.setdefault("dates_extracted", {})
        groq_result.setdefault("fraud_signals", [])
        groq_result.setdefault("country", "MAROC")
        groq_result.setdefault("doc_type", "UNKNOWN")

        # Fraud signals from technical report (signals only)
        if tech_report.get("potential_tampering"):
            fraud_signals.append(
                f"Suspicious metadata/editor detected: {tech_report.get('editor_detected')}"
            )
        if tech_report.get("font_count", 0) > 8:
            fraud_signals.append(f"High font variety: {tech_report.get('font_count')} fonts")

        # Dates coherence (if present)
        dates_ext = groq_result.get("dates_extracted", {})
        start = (dates_ext.get("start_date") or "").strip()
        end = (dates_ext.get("end_date") or "").strip()

        if start and end:
            is_coh, msg = validate_dates_coherence(start, end)
            groq_result["dates_extracted"]["dates_coherent"] = bool(is_coh)
            if not is_coh:
                format_errors.append(msg)
        else:
            # Not always mandatory for every doc, but it reduces auto-accept likelihood
            groq_result["dates_extracted"].setdefault("dates_coherent", True)

        extracted = groq_result.get("extracted_data", {})

        # Defaults for validations
        fv = groq_result["format_validation"]
        fv.setdefault("cin_format_valid", True)
        fv.setdefault("iban_format_valid", True)
        fv.setdefault("rib_format_valid", True)
        fv.setdefault("dates_format_valid", True)  # you can refine later

        # CIN validation (beneficiary)
        cin = (extracted.get("beneficiary_cin") or "").strip()
        if cin:
            is_valid_cin, cin_msg = validate_cin_morocco(cin)
            fv["cin_format_valid"] = bool(is_valid_cin)
            if not is_valid_cin:
                format_errors.append(cin_msg)
        else:
            fv["cin_format_valid"] = False
            format_errors.append("CIN bénéficiaire manquant.")

        # Bank data: accept either RIB or IBAN, but must exist for payment
        rib = (extracted.get("bank_rib") or "").strip()
        iban = (extracted.get("bank_iban") or "").strip()

        # Backward compatibility if your LLM returned beneficiary_rib
        if not rib and not iban:
            legacy = (extracted.get("beneficiary_rib") or "").strip()
            if legacy:
                if legacy.upper().startswith("MA"):
                    iban = legacy
                    extracted["bank_iban"] = legacy
                else:
                    rib = legacy
                    extracted["bank_rib"] = legacy

        # IBAN validation (only if present)
        if iban:
            is_valid_iban, iban_msg = validate_iban(iban)
            fv["iban_format_valid"] = bool(is_valid_iban)
            if not is_valid_iban:
                format_errors.append(iban_msg)
        else:
            fv["iban_format_valid"] = True  # absence is OK if RIB exists

        # RIB validation (if function exists)
        if rib:
            try:
                from utils import validate_rib_morocco  # optional in your utils.py

                is_valid_rib, rib_msg = validate_rib_morocco(rib)
                fv["rib_format_valid"] = bool(is_valid_rib)
                if not is_valid_rib:
                    format_errors.append(rib_msg)
            except Exception:
                # If not implemented yet, we only mark as present
                fv["rib_format_valid"] = True
        else:
            fv["rib_format_valid"] = True  # absence is OK if IBAN exists

        if not rib and not iban:
            format_errors.append("RIB/IBAN manquant (paiement impossible).")

        # Score adjustment
        original_score = int(groq_result.get("score", 50) or 50)
        penalty = (len(format_errors) * 5) + (len(fraud_signals) * 10)
        final_score = max(0, original_score - penalty)
        groq_result["score"] = final_score

        # Attach fraud signals
        groq_result["fraud_suspected"] = len(fraud_signals) > 0
        groq_result["fraud_signals"] = list(
            set(groq_result.get("fraud_signals", []) + fraud_signals)
        )

        # Decision rule: NEVER REJECT automatically
        has_bank_ok = bool(rib or iban) and (fv.get("rib_format_valid", True) and fv.get("iban_format_valid", True))
        has_cin_ok = fv.get("cin_format_valid", False)

        # ACCEPT only if strong confidence + no fraud + no format errors
        if final_score >= 90 and has_bank_ok and has_cin_ok and not groq_result["fraud_suspected"] and len(format_errors) == 0:
            groq_result["decision"] = "ACCEPT"
        else:
            groq_result["decision"] = "REVIEW"

        # Human-readable reason enrichment
        reasons = []
        if format_errors:
            reasons.append("Champs/Formats à vérifier: " + "; ".join(format_errors))
        if groq_result["fraud_suspected"]:
            reasons.append("Suspicion fraude (à confirmer humain): " + "; ".join(groq_result["fraud_signals"]))

        if reasons:
            existing = (groq_result.get("reason") or "").strip()
            extra = " | ".join(reasons)
            groq_result["reason"] = (existing + " | " + extra).strip(" |")

        # Keep compatibility field if your app expects it
        groq_result["is_valid"] = (groq_result["decision"] == "ACCEPT")

        return groq_result
