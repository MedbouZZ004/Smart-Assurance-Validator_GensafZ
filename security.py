"""
security.py - Sécurité & conformité (POC) pour Life Savings / Succession Document Validator

Objectifs:
- Chiffrement (Fernet) pour données sensibles si besoin
- Masquage systématique (logs / audit / UI)
- Audit JSONL sans fuite de CIN/RIB/IBAN en clair
- Déduplication par fingerprint
- Auth simple (POC) sans mot de passe en dur
"""

import os
import json
import hashlib
import logging
import re
from datetime import datetime
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# =========================
# Masking (CRITIQUE)
# =========================

SENSITIVE_KEYS = {
    "beneficiary_cin", "deceased_cin",
    "beneficiary_rib", "bank_rib",
    "beneficiary_iban", "bank_iban",
    "policy_number", "contract_number",
}

def mask_value(value: str, keep_last: int = 4) -> str:
    if value is None:
        return ""
    v = str(value).strip()
    if not v:
        return ""
    # keep last N chars
    if len(v) <= keep_last:
        return "*" * len(v)
    return "*" * (len(v) - keep_last) + v[-keep_last:]

def mask_iban(iban: str) -> str:
    iban = re.sub(r"\s+", "", (iban or "")).upper()
    if not iban:
        return ""
    # show first 4 + last 4
    if len(iban) <= 10:
        return mask_value(iban, keep_last=4)
    return iban[:4] + "*" * (len(iban) - 8) + iban[-4:]

def mask_rib(rib: str) -> str:
    digits = re.sub(r"\D", "", (rib or ""))
    if not digits:
        return ""
    return mask_value(digits, keep_last=4)

def sanitize_dict(d: dict) -> dict:
    """
    Mask sensitive fields inside a dict.
    Never return CIN/RIB/IBAN/policy_number in clear.
    """
    if not isinstance(d, dict):
        return {}

    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = sanitize_dict(v)
            continue
        if isinstance(v, list):
            # sanitize list items if dict
            new_list = []
            for item in v:
                new_list.append(sanitize_dict(item) if isinstance(item, dict) else item)
            out[k] = new_list
            continue

        key = str(k)

        if key in {"bank_iban", "beneficiary_iban"}:
            out[key] = mask_iban(str(v))
        elif key in {"bank_rib", "beneficiary_rib"}:
            out[key] = mask_rib(str(v))
        elif key in {"beneficiary_cin", "deceased_cin"}:
            out[key] = mask_value(str(v), keep_last=3)
        elif key in {"policy_number", "contract_number"}:
            out[key] = mask_value(str(v), keep_last=4)
        else:
            out[key] = v

    return out


# =========================
# Encryption (optional POC)
# =========================

class EncryptionManager:
    """Chiffrement/déchiffrement pour stockage local (POC)."""

    def __init__(self, key_path: str = ".encryption_key"):
        self.key_path = key_path
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                return f.read()

        key = Fernet.generate_key()
        with open(self.key_path, "wb") as f:
            f.write(key)
        try:
            os.chmod(self.key_path, 0o600)
        except Exception:
            pass
        logger.info("Nouvelle clé de chiffrement générée")
        return key

    def encrypt_file(self, file_path: str, output_path: str = None) -> str:
        if output_path is None:
            output_path = file_path + ".encrypted"
        with open(file_path, "rb") as f:
            plaintext = f.read()
        ciphertext = self.cipher.encrypt(plaintext)
        with open(output_path, "wb") as f:
            f.write(ciphertext)
        return output_path

    def decrypt_file(self, encrypted_path: str, output_path: str = None) -> str:
        if output_path is None:
            output_path = encrypted_path.replace(".encrypted", ".decrypted")
        with open(encrypted_path, "rb") as f:
            ciphertext = f.read()
        plaintext = self.cipher.decrypt(ciphertext)
        with open(output_path, "wb") as f:
            f.write(plaintext)
        return output_path

    def encrypt_data(self, data: str) -> str:
        return self.cipher.encrypt((data or "").encode()).decode()

    def decrypt_data(self, encrypted_data: str) -> str:
        return self.cipher.decrypt((encrypted_data or "").encode()).decode()


# =========================
# Audit JSONL (safe)
# =========================

class AuditLogger:
    """
    Audit JSONL sans fuite de données sensibles.
    extracted_fields est automatiquement masqué.
    """

    def __init__(self, log_file: str = "logs/audit_trail.jsonl"):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        self.log_file = log_file

    def log_decision(
        self,
        case_id: str,
        file_name: str,
        file_hash: str,
        score: int,
        decision: str,              # ACCEPT / REVIEW
        fraud_suspected: bool,
        doc_type: str,
        extracted_fields: dict = None,
        reason: str = ""
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "case_id": case_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "score": int(score),
            "decision": decision,
            "fraud_suspected": bool(fraud_suspected),
            "doc_type": doc_type,
            "reason": reason,
            "extracted_fields": sanitize_dict(extracted_fields or {}),
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent_decisions(self, limit: int = 100) -> list:
        decisions = []
        if not os.path.exists(self.log_file):
            return decisions

        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines[-limit:]:
            try:
                decisions.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return decisions


# =========================
# Auth (POC)
# =========================

class SimpleAuth:
    """
    Auth POC:
    - No hardcoded password.
    - Read ADMIN_USER and ADMIN_PASS_HASH from env.
    """
    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256((password or "").encode()).hexdigest()

    @staticmethod
    def verify_credentials(username: str, password: str) -> bool:
        admin_user = os.getenv("ADMIN_USER", "")
        admin_pass_hash = os.getenv("ADMIN_PASS_HASH", "")

        if not admin_user or not admin_pass_hash:
            # If not configured, deny by default (safer)
            return False

        if username != admin_user:
            return False

        return admin_pass_hash == SimpleAuth.hash_password(password)


# =========================
# Fingerprint / Dedup
# =========================

class FileFingerprintManager:
    def __init__(self, fingerprint_db: str = "fingerprints.json"):
        self.db_file = fingerprint_db
        self.fingerprints = self._load_db()

    def _load_db(self) -> dict:
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_db(self):
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(self.fingerprints, f, indent=2, ensure_ascii=False)

    def compute_fingerprint(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_duplicate(self, file_path: str) -> tuple[bool, str]:
        fp = self.compute_fingerprint(file_path)
        if fp in self.fingerprints:
            return True, self.fingerprints[fp].get("decision", "UNKNOWN")
        return False, ""

    def register_fingerprint(self, file_path: str, decision: str, score: int):
        fp = self.compute_fingerprint(file_path)
        self.fingerprints[fp] = {
            "timestamp": datetime.now().isoformat(),
            "decision": decision,
            "score": int(score)
        }
        self._save_db()


# =========================
# GDPR / anonymization
# =========================

class GDPRCompliance:
    @staticmethod
    def can_process_data(consent_given: bool, purpose: str) -> bool:
        required_purposes = {"insurance_validation", "legal_audit"}
        return bool(consent_given) and (purpose in required_purposes)

    @staticmethod
    def anonymize_record(extracted_data: dict) -> dict:
        """
        For dataset/feedback: remove direct identifiers.
        Keep only non-identifying signals.
        """
        if not isinstance(extracted_data, dict):
            return {}

        redacted = {}
        for k, v in extracted_data.items():
            if k in SENSITIVE_KEYS or k in {"beneficiary_name", "deceased_name"}:
                redacted[k] = "***REDACTED***"
            else:
                redacted[k] = v
        return redacted


# =========================
# Initialization
# =========================

def initialize_security():
    os.makedirs("logs", exist_ok=True)
    encryption = EncryptionManager()
    audit = AuditLogger()
    fingerprints = FileFingerprintManager()

    logger.info("Modules de sécurité initialisés")
    return {
        "encryption": encryption,
        "audit": audit,
        "fingerprints": fingerprints
    }
