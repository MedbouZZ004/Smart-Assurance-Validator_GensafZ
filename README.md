Life Savings & Succession Document Validator
Overview

This project is an intelligent document validation system designed for life savings insurance (épargne-vie) in a succession context.
Its goal is to automatically analyze, verify, and validate insurance claim documents after a death, while detecting inconsistencies, missing data, or potential fraud.

The system accelerates processing for valid cases and safely redirects complex or suspicious cases to a human reviewer.

## 🎯 Key Features

✅ **Multi-Document Validation** - Validates 4 required document types simultaneously  
✅ **Transparent Scoring Rules** - Clear, logical deductions for every decision  
✅ **Cross-Validation** - Compares data across documents to detect inconsistencies  
✅ **Fraud Detection** - Identifies edited/tampered documents using technical analysis  
✅ **OCR + AI Extraction** - Extracts text from PDF, PNG, JPG automatically  
✅ **Automatic Archiving** - Stores files in validated_docs or review_needed folders  
✅ **Security & Privacy** - Local processing, no sensitive data exposure  
✅ **Audit Trail** - Complete logging of all validation decisions  

## Problem Context

In life insurance and savings contracts, claim processing after a death is often slow and manual. Files usually contain multiple documents, and errors or fraud can lead to financial loss, legal issues, or delays for beneficiaries.

This project addresses these challenges by automating the first level of document analysis, while keeping humans in the loop for final decisions when needed.

## What the System Does

The system receives a case file composed of multiple documents (PDF, PNG, JPEG).
It then:

1. **Identifies** the type of each document
2. **Reads and extracts** the relevant information
3. **Compares** data across documents
4. **Detects** inconsistencies or suspicious elements
5. **Decides** whether the case can be validated or must be reviewed

## Documents Supported (Succession / Épargne-Vie)

The system is designed to handle the following documents:

1. **National ID** (CNI / Passport) - Identity verification
2. **Death Certificate** - Confirms death and provides details
3. **Life Savings Insurance Contract** (épargne-vie / policy) - Coverage verification
4. **Bank Account Details** (RIB / IBAN) - Payment destination
5. **Proof of Residence** (optional) - Address verification

## 🔢 Scoring System (Detailed)

### Individual Document Score (0-100)

Applied to each document before cross-validation.

#### Scoring Rules for Individual Documents

| Rule | Condition | Deduction | Impact |
|------|-----------|-----------|--------|
| **Fraud Detection** | Document tampered/edited OR technical tampering detected | -50 | Critical |
| **Suspicious Metadata** | Photoshop, Canva, GIMP, Illustrator detected in PDF | -10 | Major |
| **Font Inconsistency** | More than 8 different fonts detected | -5 | Minor |
| **Missing Critical Field** | Required field is empty or invalid | -10 each (max -40) | Major |

#### Example: Individual Document Score

**CNI/Passport with 1 missing field**

```
Base Score:                                      100 points
- Photoshop editor detected:                     -10 points
- Missing beneficiary_birth_date:               -10 points
──────────────────────────────────────────────────────────
Final Confidence Score:                          80 points ✅
```

### Cross-Validation Score (0-100)

Applied after all documents are individually validated.

#### Scoring Rules for Cross-Validation

| # | Rule | Condition | Deduction | Logic |
|---|------|-----------|-----------|-------|
| 1️⃣ | **Fraud Detection** | Any document shows tampering or technical suspicion | -50 | Cannot process fraudulent doc |
| 2️⃣ | **Missing Critical Docs** | Missing Death Cert, Contract, or Bank Account | -15 | Cannot verify claim |
| 3️⃣ | **Missing Critical Fields** | Key fields empty across multiple documents | -15 | Incomplete claim |
| 4️⃣ | **Low Confidence Docs** | Any document confidence score < 60% | -10 | Unreliable extraction |
| 5️⃣ | **Name Mismatches** | Names don't match across documents (deceased ≠ subscriber, etc.) | -20 each (max -60) | Identity inconsistency |
| 6️⃣ | **Date Logic Invalid** | Death date before contract effective date | -25 | Coverage period mismatch |

#### Decision Thresholds

```
IF overall_score >= 70:
   Status = VALID
   Recommendation = ACCEPT ✅
   Action = Move to validated_docs/

ELSE IF 50 <= overall_score < 70:
   Status = QUESTIONABLE
   Recommendation = INVESTIGATE ⚠️
   Action = Requires manual review in review_needed/

ELSE IF overall_score < 50:
   Status = INVALID
   Recommendation = REJECT ❌
   Action = Requires investigation
```

### Example: Complete Cross-Validation Scoring

#### ✅ EXAMPLE 1: Clean Claim (Score: 100)

**Scenario**: All documents complete, all names match, no fraud detected

```
Base Score:                                           100
- Fraud Detected:                                      -0 (no fraud)
- Missing Critical Documents:                         -0 (all present)
- Missing Critical Fields:                            -0 (all complete)
- Low Confidence Documents:                           -0 (all ≥ 70%)
- Name Mismatches:                                    -0 (all match)
- Death Date Outside Contract Period:                 -0 (date valid)
─────────────────────────────────────────────────────────
FINAL SCORE: 100 ✅ ACCEPT

Result: Documents moved to validated_docs/
```

**Why it passes**:
- ✅ All names match perfectly across documents
- ✅ Death date within contract validity period
- ✅ All critical documents present
- ✅ All critical fields present and complete
- ✅ No fraud indicators detected
- ✅ All documents have high confidence scores

---

#### ⚠️ EXAMPLE 2: Suspicious Claim (Score: 55)

**Scenario**: Beneficiary name on contract doesn't match bank account holder

```
Base Score:                                           100
- Fraud Detected:                                      -0 (no fraud)
- Missing Critical Documents:                         -0 (all present)
- Missing Critical Fields:                            -0 (all complete)
- Low Confidence Documents:                           -10 (Bank doc at 55%)
- Name Mismatches:                                    -20 (Beneficiary ≠ Account Holder)
- Death Date Outside Contract Period:                 -0 (date valid)
─────────────────────────────────────────────────────────
FINAL SCORE: 55 ⚠️ INVESTIGATE

Result: Moved to review_needed/ for manual verification
```

**Why it's questionable**:
- ⚠️ Beneficiary name ≠ Bank account holder name
- ⚠️ Low confidence in bank document extraction
- ⚠️ Could be legitimate (power of attorney, trustee), but needs verification

**What to do**:
1. Contact claimant to clarify beneficiary situation
2. Request clearer bank document scan
3. Verify legal authorization for transfer to different person

---

#### ❌ EXAMPLE 3: Invalid Claim (Score: 30)

**Scenario**: Death occurred before insurance contract started

```
Base Score:                                           100
- Fraud Detected:                                      -0 (no fraud)
- Missing Critical Documents:                         -0 (all present)
- Missing Critical Fields:                           -15 (missing policy number)
- Low Confidence Documents:                          -10 (CNI at 45%)
- Name Mismatches:                                    -0 (all match)
- Death Date Outside Contract Period:                -25 (death before contract start)
─────────────────────────────────────────────────────────
FINAL SCORE: 30 ❌ REJECT

Death date: 15/12/2023
Contract start date: 01/01/2024
Status: ❌ NO COVERAGE (Death before contract effective)
```

**Why it fails**:
- ❌ Death occurred BEFORE insurance contract started
- ❌ No active coverage at time of death
- ❌ Claim cannot be processed per policy terms
- ❌ Missing policy number in contract

**Action**: Reject claim + Inform beneficiary that death was before coverage commenced

---

## 📖 Quick Start Guide

### 1. Installation

```bash
# Install dependencies
pip install streamlit pymupdf easyocr groq python-dotenv

# Create required directories
mkdir validated_docs review_needed invalid_docs logs

# Create .env file with your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env
```

### 2. Get Groq API Key

1. Go to https://console.groq.com
2. Sign up (free account)
3. Create new API key
4. Add to `.env` file

### 3. Run the Application

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`

### 4. Upload Documents

1. Click upload area
2. Select 4 required documents:
   - CNI/Passport
   - Death Certificate
   - Insurance Contract
   - Bank Account (RIB/IBAN)
3. Click "Lancer l'audit IA (dossier)"

### 5. Review Results

The system displays:
- Individual document analysis (per document)
- Cross-validation results (across documents)
- Score breakdown with logical deductions
- Final recommendation (ACCEPT/REVIEW/REJECT)

---

## 📁 File Structure

```
Smart-Assurance-ValidatorX/
│
├── 🚀 APPLICATION FILES
│   ├── app.py                          # Main Streamlit app (USE THIS!)
│   ├── validator.py                    # Validation engine + cross-validation
│   └── security.py                     # Security & audit functions
│
├── 🔧 UTILITIES
│   ├── utils.py                        # Validation helpers (IBAN, CIN, dates)
│   └── fingerprints.json               # Duplicate detection cache
│
├── 📁 DOCUMENT STORAGE
│   ├── validated_docs/                 # ✅ ACCEPT decisions (auto-organized by case_id)
│   ├── review_needed/                  # ⏳ REVIEW decisions (requires manual review)
│   ├── invalid_docs/                   # ❌ Manual rejections only
│   └── uploads_tmp/                    # Temporary files (auto-cleaned)
│
├── 📊 AUDIT & LOGS
│   ├── audit_trail.db                  # SQLite database of all decisions
│   └── logs/audit.log                  # Text log file
│
├── ⚙️ CONFIGURATION
│   └── .env                            # API keys (CREATE THIS!)
│
└── 📚 DOCUMENTATION
    ├── README.md                       # This file
    └── requirements.txt                # Python dependencies
```

---

## 🔐 Security & Privacy

- ✅ Files stored locally (validated_docs, review_needed, invalid_docs)
- ✅ Temporary files auto-deleted after processing
- ✅ No data sent to external services except Groq API
- ✅ GROQ_API_KEY stored in local .env (never in code)
- ✅ Audit trail stored locally (no personally identifiable information logged)
- ✅ File hashing for duplicate detection
- ✅ Fingerprint-based duplicate prevention

---

## 🛠️ Technical Implementation

### Architecture

```
┌─────────────────────┐
│   Streamlit UI      │ (app.py)
│  - File upload      │
│  - Results display  │
└──────────┬──────────┘
           │
┌──────────▼──────────────────────┐
│  Document Processing Pipeline   │
├─────────────────────────────────┤
│ 1. Extract: OCR + Structure     │ (validator.py:extract_all)
│ 2. Analyze: Technical integrity │ (validator.py:analyze_technical_integrity)
│ 3. Classify: Document type      │ (validator.py:validate_with_groq)
│ 4. Extract: Fields via LLM      │ (Groq API - llama-3.3-70b-versatile)
│ 5. Validate: Format checks      │ (validator.py:_validate_extracted_data)
└──────────┬──────────────────────┘
           │
┌──────────▼──────────────────────┐
│  Cross-Validation Module (NEW)  │
├─────────────────────────────────┤
│ 1. Compute Individual Scores    │ (compute_individual_confidence_score)
│ 2. Cross-validate Documents     │ (cross_validate_documents)
│ 3. Apply Logical Scoring Rules  │ (compute_cross_validation_score)
│ 4. Generate Score Breakdown     │ (score_breakdown with deductions)
└──────────┬──────────────────────┘
           │
┌──────────▼──────────────────────┐
│  Decision & Storage             │
├─────────────────────────────────┤
│ IF score >= 70: ACCEPT          │
│ ELSE IF score >= 50: REVIEW     │
│ ELSE: REJECT                    │
│                                 │
│ Store in appropriate folder     │
│ Log to audit_trail.db           │
└─────────────────────────────────┘
```

### Validation Rules Implementation

All rules are implemented in `validator.py`:

- **Individual Scoring**: `compute_individual_confidence_score()` method
- **Cross-Validation**: `compute_cross_validation_score()` method
- **Name Matching**: `_names_match()` method with fuzzy logic
- **Batch Processing**: `process_document_batch()` method

---

## 📋 API Integration

The system uses **Groq API** with `llama-3.3-70b-versatile` model:

- **Fast Processing**: Llama 3.3-70B handles complex extraction efficiently
- **JSON Response Format**: Structured output for reliable parsing
- **Temperature**: Set to 0 for deterministic, consistent results
- **Model**: llama-3.3-70b-versatile (fast & accurate)

**API Call Example**:
```python
chat = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
    response_format={"type": "json_object"}
)
```

---

## 🧪 Testing & Validation

### Manual Test Workflow

1. Run: `streamlit run app.py`
2. Upload test documents
3. Click "Lancer l'audit IA (dossier)"
4. Review individual and cross-validation results
5. Check case folder in `validated_docs/` or `review_needed/`

### Test Cases Included

- ✅ Valid complete dossier → Score 100 → ACCEPT
- ⚠️ Name mismatch → Score 55 → REVIEW
- ❌ Death before coverage → Score 30 → REJECT
- 🚩 Fraud detected → Score 0 → REVIEW

---

## ⚙️ Configuration & Customization

### Change LLM Model

Edit `app.py` or `validator.py`:

```python
model="llama-3.3-70b-versatile"  # Current
# Other options:
model="llama-3.1-70b-versatile"
model="mixtral-8x7b-32768"
```

### Adjust Fraud Detection Sensitivity

Edit `validator.py` `analyze_technical_integrity()`:

```python
# Font threshold (default: 8)
potential_tampering = bool(is_suspicious_tool or font_count > 6)  # More strict

# Add more fraud tools
fraud_tools = ["canva", "photoshop", "figma", "custom_tool"]
```

### Modify Scoring Rules

Edit `validator.py` `compute_cross_validation_score()`:

```python
# Example: Increase name mismatch penalty
name_deduction = min(len(all_mismatches) * 30, 80)  # Was 20, now 30

# Example: Add new validation rule
if some_condition:
    score -= 15
    deductions.append("New rule description (-15)")
```

---

## 🔍 Troubleshooting

### "GROQ_API_KEY not found"

**Solution**: Create `.env` file with your API key

```bash
echo "GROQ_API_KEY=your_key_here" > .env
```

### "ModuleNotFoundError: No module named..."

**Solution**: Install all dependencies

```bash
pip install streamlit pymupdf easyocr groq python-dotenv
```

### OCR is very slow

**Normal**: First run downloads ~500MB OCR model (5-10 minutes).  
**Solution**: Be patient on first run. Subsequent runs are much faster (model is cached).

### Scores always low

**Common Causes**:
- Missing documents → Add all required documents
- Names don't match → Verify names are identical across documents
- Fraud detected → Check document quality, avoid edited PDFs
- Date issues → Ensure death date is after contract start date

---

## 📈 Future Enhancements

- [ ] Support for more document types
- [ ] Multi-language support (Arabic, Spanish, etc.)
- [ ] Advanced fraud detection (image forensics)
- [ ] Batch processing UI for multiple cases
- [ ] Export results to PDF reports
- [ ] Integration with external databases
- [ ] Machine learning model for scoring optimization

---

## 📞 Support & Contact

For issues or questions:

1. Check the troubleshooting section above
2. Review logs in `logs/audit.log`
3. Check audit trail: `audit_trail.db`
4. Verify all documents are clear and readable
5. Ensure .env file exists with valid API key

---

## 📄 License & Usage Policy

- **NEVER auto-reject**: System only recommends ACCEPT or REVIEW
- **Human-in-the-loop**: Final decisions always reviewed by authorized personnel
- **Privacy first**: All data processed locally, no external storage
- **Audit trail**: Complete logging for compliance and verification

---

## 🚀 Getting Started Checklist

- [ ] Install Python 3.8+
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Get Groq API key at https://console.groq.com
- [ ] Create `.env` file with GROQ_API_KEY
- [ ] Create required directories: `mkdir validated_docs review_needed invalid_docs logs`
- [ ] Run app: `streamlit run app.py`
- [ ] Upload test documents
- [ ] Review results and scoring breakdown
- [ ] Check audit trail in `audit_trail.db`

---

## Version & Updates

**Current Version**: 2.0 (Multi-Document Cross-Validation)

**Recent Changes**:
- ✅ Added transparent scoring rules
- ✅ Added cross-validation logic
- ✅ Added detailed scoring breakdown display
- ✅ Added fraud detection improvements
- ✅ Added confidence score computation
- ✅ Enhanced UI with cross-validation results

---

**Last Updated**: January 2026  
**Status**: Production Ready ✅

Bank RIB (with IBAN if available) for payment

Power of attorney or notarized document (special or complex cases)

A case cannot be fully validated if mandatory documents are missing.



Key Data Extracted

From these documents, the system extracts and analyzes:

Names and surnames

National ID numbers

Dates (birth, death, contract subscription)

Insurance contract number

Beneficiary identity

Bank information (RIB / IBAN)

Legal references (if present)



Validation Logic

The system compares information between documents to ensure consistency.
Examples:

The deceased’s identity must match across ID, contract, and death certificate

The beneficiary requesting payment must match the beneficiary stated in the contract

The bank account (RIB) must belong to the beneficiary or be legally justified



Decision Outcomes

Each case results in one of three decisions:

ACCEPT
All required documents are present and data is consistent. The case can be processed automatically.

REVIEW
Missing documents, minor inconsistencies, unclear information, or low document quality. The case is sent to a human agent.
Strong indicators of fraud or major inconsistencies that invalidate the claim.



Why Some Cases Are Sent to a Human

The system is not designed to replace humans.
It deliberately sends cases to human reviewers when:

a required document is missing

extracted data is incomplete or ambiguous

documents contain conflicting information

there are signs of document manipulation

This ensures fairness, safety, and legal compliance.



Security & Privacy

Because the system handles sensitive personal and financial data:

sensitive fields (ID numbers, RIB, IBAN) are masked in logs and UI

data should be encrypted at rest and in transit

all decisions are traceable through an audit trail



Project Scope

This project is intended for:

academic projects

hackathons

proof-of-concepts

early-stage validation systems for insurance workflows

It is not a production-ready insurance system, but a structured and realistic demonstration of how AI can assist document validation in life insurance succession!!!!!!



High-Level Workflow

Document upload (PDF / image)

Document type detection

Text extraction (OCR)

Structured data extraction

Cross-document consistency checks

Risk and anomaly detection

Automatic decision or human review



Summary

This project demonstrates how artificial intelligence can improve the speed, reliability, and security of épargne-vie succession processing, by validating correct cases automatically and intelligently flagging complex cases for human review.

