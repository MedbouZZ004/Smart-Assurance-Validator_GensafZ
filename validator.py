import os
import re
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
    validate_date_format,
    validate_rib_morocco,
)

load_dotenv()


class InsuranceValidator:
    """
    POLICY:
    - NEVER auto-reject
    - ONLY: ACCEPT or REVIEW
    """

    def __init__(self):
        self.reader = easyocr.Reader(["fr", "en"])
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY non trouvée ! Vérifiez votre fichier .env.")
        self.client = Groq(api_key=api_key)
        self.groq_timeout = 30

    # -----------------------------
    # Fraud / Integrity (PDF level)
    # -----------------------------
    def analyze_technical_integrity(self, doc, file_path: str) -> dict:
        metadata = doc.metadata or {}

        fraud_tools = ["canva", "photoshop", "illustrator", "gimp", "inkscape", "adobe acrobat pro"]
        creator = (metadata.get("creator") or "").lower()
        producer = (metadata.get("producer") or "").lower()
        is_suspicious_tool = any(tool in creator or tool in producer for tool in fraud_tools)

        fonts = []
        for page in doc:
            fonts.extend([f[3] for f in page.get_fonts()])
        font_count = len(set(fonts))

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
        """
        PDF only (current). If you upload PNG/JPG, app should convert to PDF or you add support later.
        """
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
            text_results.extend(self.reader.readtext(pix.tobytes("png"), detail=0))

        return " ".join(text_results), structure, tech_report

# Penalize score if technical tampering is suspected
        final_score = int(analysis.get("score", 0))
        if tech["potential_tampering"]:
            final_score = max(0, final_score - 30)

        return {
            "category": analysis.get("category"),
            "nom": analysis.get("nom"),
            "score": final_score,
            "tech_report": tech
        }
    # -----------------------------
    # LLM extraction + validation
    # -----------------------------
    def validate_with_groq(self, text: str, structure: dict, tech_report: dict) -> dict:
        """
        OBJECTIF :
        1) Classifier le document...
        2) Extraire les noms complets SANS supprimer les particules (ex: garder 'El', 'Ait', 'Ben').
           Si le texte dit 'Sara El Idrissi', n'écris pas 'Sara Idrissi'.
        ...
        """

        """
        LLM extracts fields + proposes ACCEPT/REVIEW.
        Post-validation enforces policy and Morocco checks.
        """
        prompt = f"""
RÔLE : Auditeur Assurance (Contexte MAROC) - Dossiers épargne-vie / succession.
IMPORTANT : Tu ne rejettes JAMAIS. Décision = "ACCEPT" ou "REVIEW" seulement.

DONNÉES TECHNIQUES (SIGNAL UNIQUEMENT) :
- Structure : {structure}
- Suspicion technique : {tech_report.get('potential_tampering')} (éditeur : {tech_report.get('editor_detected')})
- Nombre de polices distinctes : {tech_report.get('font_count')}

TEXTE OCR (extrait) :
{text[:4500]}

OBJECTIF :
1) Classifier le document: ID / BANK / DEATH / LIFE_CONTRACT (ou UNKNOWN)
2) Extraire les champs requis
3) Proposer une décision "ACCEPT" seulement si champs critiques présents + formats OK + pas de signaux techniques

CHAMPS À EXTRAIRE :

[ID - CNI/PASSEPORT]
- beneficiary_name
- beneficiary_cin
- beneficiary_birth_date
- id_document_number
- id_expiry_date

[BANK - RIB/IBAN]
- bank_account_holder
- bank_iban (si présent)
- bank_rib (si présent)
- bank_bic
- bank_name

[DEATH - CERTIFICAT DE DÉCÈS]
- deceased_name
- death_date
- death_place
- death_act_number

[LIFE_CONTRACT - CONTRAT ÉPARGNE-VIE]
- policy_number
- subscriber_name
- beneficiary_name
- beneficiary_cin (si présent)
- contract_effective_date
- capital

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
    "subscriber_name": "",
    "deceased_name": "",
    "beneficiary_name": "",
    "beneficiary_cin": "",
    "beneficiary_birth_date": "",
    "id_document_number": "",
    "id_expiry_date": "",
    "bank_account_holder": "",
    "bank_rib": "",
    "bank_iban": "",
    "bank_bic": "",
    "bank_name": "",
    "death_date": "",
    "death_place": "",
    "death_act_number": "",
    "contract_effective_date": "",
    "capital": ""
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
            # NEVER reject: errors => REVIEW
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
    # Post validation (strict policy)
    # -----------------------------
    def _validate_extracted_data(self, groq_result: dict, tech_report: dict | None = None) -> dict:
        """
        Post-traitement (sans auto-reject):
        - Validations adaptées au type (ID/BANK/DEATH/LIFE_CONTRACT)
        - Tech signals => REVIEW
        """
        tech_report = tech_report or {}
        format_errors = []
        fraud_signals = []

        groq_result = groq_result or {}
        groq_result.setdefault("format_validation", {})
        groq_result.setdefault("extracted_data", {})
        groq_result.setdefault("dates_extracted", {})
        groq_result.setdefault("fraud_signals", [])
        groq_result.setdefault("country", "MAROC")
        groq_result.setdefault("doc_type", "UNKNOWN")

        extracted = groq_result.get("extracted_data", {}) or {}

        # normalize doc_type to one of 4
        raw_dt = (groq_result.get("doc_type") or "UNKNOWN").strip().upper()
        dt = raw_dt
        if "CNI" in dt or "CNIE" in dt or "PASSPORT" in dt or "PASSEPORT" in dt or "IDENT" in dt:
            dt = "ID"
        elif "RIB" in dt or "IBAN" in dt or "BANK" in dt or "BANQUE" in dt:
            dt = "BANK"
        elif "DECES" in dt or "DÉCÈS" in dt or "DEATH" in dt or "CERTIFICAT" in dt:
            dt = "DEATH"
        elif "ASSURANCE" in dt or "CONTRAT" in dt or "POLICE" in dt or "LIFE" in dt:
            dt = "LIFE_CONTRACT"
        elif dt not in ["ID", "BANK", "DEATH", "LIFE_CONTRACT"]:
            dt = "UNKNOWN"

        groq_result["doc_type"] = dt

        fv = groq_result["format_validation"]
        fv.setdefault("cin_format_valid", True)
        fv.setdefault("iban_format_valid", True)
        fv.setdefault("rib_format_valid", True)
        fv.setdefault("dates_format_valid", True)

        # tech fraud signals (signals only)
        if tech_report.get("potential_tampering"):
            fraud_signals.append(f"Suspicious editor: {tech_report.get('editor_detected')}")
        if tech_report.get("font_count", 0) > 8:
            fraud_signals.append(f"High font variety: {tech_report.get('font_count')} fonts")

        # dates coherence if both exist (optional)
        dates_ext = groq_result.get("dates_extracted", {}) or {}
        start = (dates_ext.get("start_date") or "").strip()
        end = (dates_ext.get("end_date") or "").strip()
        if start and end:
            is_coh, msg = validate_dates_coherence(start, end)
            groq_result["dates_extracted"]["dates_coherent"] = bool(is_coh)
            if not is_coh:
                format_errors.append(msg)

        # date format checks (only if present)
        def _check_date(field_key: str, label: str):
            v = (extracted.get(field_key) or "").strip()
            if not v:
                return
            ok, _ = validate_date_format(v)
            if not ok:
                fv["dates_format_valid"] = False
                format_errors.append(f"{label} invalide: {v}")

        _check_date("beneficiary_birth_date", "Date naissance")
        _check_date("id_expiry_date", "Date expiration ID")
        _check_date("death_date", "Date décès")
        _check_date("contract_effective_date", "Date effet contrat")

        # CIN validation: ONLY for ID/LIFE_CONTRACT
        cin = (extracted.get("beneficiary_cin") or "").strip()
        if dt in ["ID", "LIFE_CONTRACT"]:
            if cin:
                ok, msg = validate_cin_morocco(cin)
                fv["cin_format_valid"] = bool(ok)
                if not ok:
                    format_errors.append(msg)
            else:
                fv["cin_format_valid"] = False
                format_errors.append("CIN bénéficiaire manquant.")
        else:
            fv["cin_format_valid"] = True  # BANK/DEATH do not require CIN

        # IBAN/RIB validation: only if present (required at dossier-level by app)
        rib = (extracted.get("bank_rib") or "").strip()
        iban = (extracted.get("bank_iban") or "").strip()

        if iban:
            ok, msg = validate_iban(iban)
            fv["iban_format_valid"] = bool(ok)
            if not ok:
                format_errors.append(msg)
        else:
            fv["iban_format_valid"] = True

        if rib:
            ok, msg = validate_rib_morocco(rib)
            fv["rib_format_valid"] = bool(ok)
            if not ok:
                format_errors.append(msg)
        else:
            fv["rib_format_valid"] = True

        # Score adjustment
        original_score = int(groq_result.get("score", 60) or 60)
        penalty = (len(format_errors) * 6) + (len(fraud_signals) * 10)
        final_score = max(0, original_score - penalty)
        groq_result["score"] = final_score

        groq_result["fraud_suspected"] = len(fraud_signals) > 0
        groq_result["fraud_signals"] = list(set(groq_result.get("fraud_signals", []) + fraud_signals))

        # decision: never reject
        if tech_report.get("potential_tampering"):
            groq_result["decision"] = "REVIEW"

        if final_score >= 90 and not groq_result["fraud_suspected"] and len(format_errors) == 0:
            groq_result["decision"] = "ACCEPT"
        else:
            groq_result["decision"] = "REVIEW"

        # reason enrichment
        reasons = []
        if format_errors:
            reasons.append("Formats à vérifier: " + "; ".join(format_errors))
        if groq_result["fraud_suspected"]:
            reasons.append("Signaux techniques: " + "; ".join(groq_result["fraud_signals"]))

        if reasons:
            existing = (groq_result.get("reason") or "").strip()
            extra = " | ".join(reasons)
            groq_result["reason"] = (existing + " | " + extra).strip(" |")

        groq_result["is_valid"] = (groq_result["decision"] == "ACCEPT")
        return groq_result
    # ========================================
    # CROSS-VALIDATION & TRANSPARENT SCORING
    # ========================================

    def compute_individual_confidence_score(self, doc_type: str, extracted_data: dict, 
                                            tech_report: dict, fraud_detected: bool) -> int:
        """
        Compute confidence score for a single document using transparent logical rules.
        
        Scoring Rules (0-100):
        - Base: 100 points
        - Fraud Detected or Technical Tampering: -50 points
        - Missing Critical Fields: -10 per missing field (max -40)
        - Suspicious Metadata: -10 if suspicious tools detected
        - Font Inconsistency: -5 if too many fonts (>8)
        
        Returns score between 0-100
        """
        score = 100
        deductions = []
        
        # RULE 1: Fraud Detection or Technical Tampering (-50)
        if fraud_detected or tech_report.get("potential_tampering"):
            score -= 50
            deductions.append("Fraude détectée ou tampering technique (-50)")
        
        # RULE 2: Suspicious Metadata (-10)
        if tech_report.get("suspicious_metadata"):
            score -= 10
            deductions.append("Métadonnées suspectes (-10)")
        
        # RULE 3: Font Consistency (-5)
        font_count = tech_report.get("font_count", 0)
        if font_count > 8:
            score -= 5
            deductions.append(f"Cohérence de police douteuse: {font_count} polices (-5)")
        
        # RULE 4: Critical fields presence by document type
        missing_fields = []
        critical_fields_map = {
            "ID": ["beneficiary_name", "beneficiary_cin", "beneficiary_birth_date"],
            "BANK": ["bank_account_holder", "bank_iban", "bank_bic"],
            "DEATH": ["deceased_name", "death_date", "death_place"],
            "LIFE_CONTRACT": ["policy_number", "subscriber_name", "beneficiary_name", "contract_effective_date"],
        }
        
        critical_fields = critical_fields_map.get(doc_type, [])
        for field in critical_fields:
            if not extracted_data.get(field) or not str(extracted_data.get(field)).strip():
                missing_fields.append(field)
        
        # Deduct 10 points per missing critical field (max -40)
        field_deduction = min(len(missing_fields) * 10, 40)
        if missing_fields:
            score -= field_deduction
            deductions.append(f"Champs critiques manquants: {', '.join(missing_fields)} (-{field_deduction})")
        
        # Ensure score doesn't go below 0
        score = max(score, 0)
        
        return score

    def compute_cross_validation_score(self, validation_data: dict) -> dict:
        """
        Compute cross-validation score using transparent logical rules.
        
        Scoring Rules:
        - Base Score: 100 points
        - Fraud Detection: -50 if fraud indicators found
        - Missing Critical Docs: -15 if Death Cert, Contract, or RIB missing
        - Missing Critical Fields: -15 if essential fields missing
        - Low Confidence Docs: -10 if overall confidence < 60%
        - Name Mismatches: -20 per mismatch (max -60)
        - Date Logic: -25 if death date outside contract period
        
        Final Score:
        - >= 70: VALID (Accept)
        - 50-69: QUESTIONABLE (Investigate)
        - < 50: INVALID (Reject)
        """
        
        score = 100
        deductions = []
        
        # Extract key data from all documents
        deceased_name = None
        subscriber_name = None
        beneficiary_name = None
        account_holder = None
        death_date = None
        contract_start = None
        fraud_found = False
        low_confidence_docs = []
        missing_critical_docs = []
        missing_critical_fields = []
        name_mismatches = []
        date_issues = []
        
        for file_name, doc_result in validation_data.items():
            doc_type = doc_result.get("doc_type", "UNKNOWN")
            extracted = doc_result.get("extracted_data", {})
            fraud_detected = doc_result.get("fraud_suspected", False)
            confidence = doc_result.get("score", 0)
            
            # Track fraud
            if fraud_detected:
                fraud_found = True
            
            # Track low confidence
            if confidence < 60:
                low_confidence_docs.append(file_name)
            
            # Extract critical data by document type
            if doc_type == "DEATH":
                deceased_name = (extracted.get("deceased_name") or "").strip()
                death_date = (extracted.get("death_date") or "").strip()
                if not deceased_name:
                    missing_critical_fields.append(f"{file_name}: Nom du défunt manquant")
                if not death_date:
                    missing_critical_fields.append(f"{file_name}: Date de décès manquante")
            
            elif doc_type == "LIFE_CONTRACT":
                subscriber_name = (extracted.get("subscriber_name") or "").strip()
                beneficiary_name = (extracted.get("beneficiary_name") or "").strip()
                contract_start = (extracted.get("contract_effective_date") or "").strip()
                policy_num = (extracted.get("policy_number") or "").strip()
                
                if not subscriber_name:
                    missing_critical_fields.append(f"{file_name}: Nom assuré manquant")
                if not beneficiary_name:
                    missing_critical_fields.append(f"{file_name}: Nom bénéficiaire manquant")
                if not policy_num:
                    missing_critical_fields.append(f"{file_name}: Numéro de police manquant")
            
            elif doc_type == "BANK":
                account_holder = (extracted.get("bank_account_holder") or "").strip()
                if not account_holder:
                    missing_critical_fields.append(f"{file_name}: Titulaire du compte manquant")
            
            elif doc_type == "ID":
                id_name = (extracted.get("beneficiary_name") or "").strip()
                if id_name and beneficiary_name:
                    if not self._names_match(id_name, beneficiary_name):
                        name_mismatches.append(f"Nom ID ({id_name}) ≠ Bénéficiaire contrat ({beneficiary_name})")
        
        # Check critical documents presence
        doc_types_present = set()
        for file_name, doc_result in validation_data.items():
            dt = doc_result.get("doc_type", "UNKNOWN")
            if dt != "UNKNOWN":
                doc_types_present.add(dt)
        
        # Critical documents for succession: Death Cert + Contract + Bank Account
        critical_docs = {"DEATH", "LIFE_CONTRACT", "BANK"}
        missing_docs = critical_docs - doc_types_present
        
        if missing_docs:
            missing_critical_docs = list(missing_docs)
        
        # RULE 1: Fraud Detection (-50 points)
        if fraud_found:
            score -= 50
            deductions.append("Fraude détectée dans un ou plusieurs documents (-50)")
        
        # RULE 2: Missing Critical Documents (-15 points)
        if missing_critical_docs:
            score -= 15
            deductions.append(f"Documents critiques manquants: {', '.join(missing_critical_docs)} (-15)")
        
        # RULE 3: Missing Critical Fields (-15 points)
        if missing_critical_fields:
            score -= 15
            deductions.append(f"Champs critiques manquants ({len(missing_critical_field)} domaines) (-15)")
        
        # RULE 4: Low Confidence Documents (-10 points)
        if low_confidence_docs:
            score -= 10
            deductions.append(f"Confiance faible: {', '.join(low_confidence_docs)} (-10)")
        
        # RULE 5: Name Consistency (-20 per mismatch, max -60)
        all_mismatches = []
        
        # Check: Deceased vs Subscriber
        if deceased_name and subscriber_name:
            if not self._names_match(deceased_name, subscriber_name):
                all_mismatches.append("deceased_name ≠ subscriber_name")
        
        # Check: Beneficiary vs Account Holder
        if beneficiary_name and account_holder:
            if not self._names_match(beneficiary_name, account_holder):
                all_mismatches.append("beneficiary_name ≠ account_holder")
        
        all_mismatches.extend(name_mismatches)
        
        # Apply name mismatch deductions (max -60)
        name_deduction = min(len(all_mismatches) * 20, 60)
        if all_mismatches:
            score -= name_deduction
            deductions.append(f"Incohérences de noms: {len(all_mismatches)} ({', '.join(all_mismatches[:2])}) (-{name_deduction})")
        
        # RULE 6: Date Logic Validity (-25 points)
        date_logic_valid = True
        
        if death_date and contract_start:
            try:
                from datetime import datetime
                death_dt = datetime.strptime(death_date.split()[0], "%d/%m/%Y") if death_date else None
                start_dt = datetime.strptime(contract_start.split()[0], "%d/%m/%Y") if contract_start else None
                
                if death_dt and start_dt:
                    # Death should be after or on contract effective date (no end date check as per policy)
                    if death_dt < start_dt:
                        date_logic_valid = False
                        date_issues.append(f"Décès ({death_date}) avant date d'effet du contrat ({contract_start})")
                        score -= 25
                        deductions.append(f"Logique de dates invalide (-25)")
            except Exception as e:
                date_logic_valid = False
                date_issues.append(f"Erreur parsing dates: {str(e)}")
                score -= 25
                deductions.append(f"Format de date invalide (-25)")
        
        # Ensure score doesn't go below 0
        score = max(score, 0)
        
        # Determine validation status
        if score >= 70:
            status = "VALID"
            recommendation = "ACCEPT"
        elif score >= 50:
            status = "QUESTIONABLE"
            recommendation = "INVESTIGATE"
        else:
            status = "INVALID"
            recommendation = "REJECT"
        
        # Build detailed reason
        if deductions:
            reason_text = "Calcul du score: " + " | ".join(deductions)
        else:
            reason_text = "Tous les critères de validation sont satisfaits."
        
        return {
            "is_valid": score > 50,
            "overall_score": score,
            "cross_validation_status": status,
            "score_breakdown": {
                "base_score": 100,
                "deductions": deductions,
                "final_score": score
            },
            "name_matches": {
                "deceased_vs_subscriber": deceased_name and subscriber_name and self._names_match(deceased_name, subscriber_name),
                "beneficiary_vs_account_holder": beneficiary_name and account_holder and self._names_match(beneficiary_name, account_holder),
                "mismatches_found": all_mismatches
            },
            "date_logic_valid": date_logic_valid,
            "date_issues": date_issues,
            "critical_documents_present": len(missing_docs) == 0,
            "missing_documents": missing_critical_docs,
            "missing_fields": missing_critical_fields,
            "fraud_indicators": ["Fraude détectée"] if fraud_found else [],
            "low_confidence_documents": low_confidence_docs,
            "discrepancies": all_mismatches + date_issues,
            "recommendation": recommendation,
            "detailed_reason": reason_text
        }

    def _names_match(self, name1: str, name2: str, threshold: float = 0.70) -> bool:
        """
        Check if two names match using fuzzy matching.
        Case-insensitive, ignores extra spaces.
        """
        n1 = re.sub(r"\s+", " ", (name1 or "").strip().lower())
        n2 = re.sub(r"\s+", " ", (name2 or "").strip().lower())
        
        if not n1 or not n2:
            return False
        
        # Exact match
        if n1 == n2:
            return True
        
        # Check if names contain same word elements
        words1 = set(re.findall(r"[a-zàâçéèêëîïôùûüÿñ]+", n1))
        words2 = set(re.findall(r"[a-zàâçéèêëîïôùûüÿñ]+", n2))
        
        if not words1 or not words2:
            return False
        
        # Calculate similarity ratio
        common = len(words1 & words2)
        total = len(words1 | words2)
        ratio = common / total if total > 0 else 0
        
        return ratio >= threshold

    def cross_validate_documents(self, documents: dict) -> dict:
        """
        Cross-validate multiple documents and compute score using logical rules.
        
        Args:
            documents: Dict with file_name as key and validation result as value
        
        Returns:
            Cross-validation result with logical rule-based score
        """
        try:
            return self.compute_cross_validation_score(documents)
        
        except Exception as e:
            return {
                "is_valid": False,
                "overall_score": 0,
                "cross_validation_status": "ERROR",
                "score_breakdown": {
                    "base_score": 100,
                    "deductions": [f"Erreur système: {str(e)}"],
                    "final_score": 0
                },
                "name_matches": {},
                "date_logic_valid": False,
                "critical_documents_present": False,
                "missing_documents": [],
                "missing_fields": [],
                "fraud_indicators": ["Erreur lors de la validation"],
                "low_confidence_documents": [],
                "discrepancies": [],
                "recommendation": "REVIEW",
                "detailed_reason": f"Erreur de validation: {str(e)}"
            }

    def process_document_batch(self, file_paths: list) -> tuple:
        """
        Process a batch of documents: validate individually, then cross-validate.
        
        Returns:
            Tuple of (individual_results dict, cross_validation_result dict)
        """
        individual_results = {}
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue
            
            file_name = os.path.basename(file_path)
            
            # Individual validation
            text, struct, tech_report = self.extract_all(file_path)
            result = self.validate_with_groq(text, struct, tech_report)
            
            # Compute individual confidence score
            fraud_detected = result.get("fraud_suspected", False) or tech_report.get("potential_tampering")
            confidence_score = self.compute_individual_confidence_score(
                result.get("doc_type", "UNKNOWN"),
                result.get("extracted_data", {}),
                tech_report,
                fraud_detected
            )
            
            result["confidence_score"] = confidence_score
            individual_results[file_name] = result
        
        # Perform cross-validation
        cross_validation_result = self.cross_validate_documents(individual_results)
        
        return individual_results, cross_validation_result