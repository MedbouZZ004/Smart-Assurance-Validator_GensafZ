# Smart Assurance Validator X 🛡️

An AI-powered document validation system designed for the insurance sector, specifically targeting the **French** and **Moroccan** markets. This tool leverages advanced OCR and Large Language Models (LLM) to extract data, verify technical integrity (fraud detection), and ensure business compliance.

## 🚀 Features

*   **Multi-Format Support:** Compatible with **PDF, PNG, and JPEG** files.
*   **Dual-Market Logic:** Specialized validation rules for:
    *   **France:** Carte Verte, Attestation d'Assurance, Constat Amiable.
    *   **Morocco:** Attestation d'Assurance, Carte Grise, Permis, Constat Amiable.
*   **AI-Powered Analysis:** Uses **Groq (Llama 3.3-70b)** for deep semantic understanding and data extraction.
*   **Fraud Detection:**
    *   **Metadata Analysis:** Detects traces of editing software (Photoshop, Canva, GIMP, etc.).
    *   **Font Consistency:** Flags documents with excessive font variations.
*   **Automated Extraction:** Extracts key business data such as Insurer, Policy Number, Dates, and Vehicle/Client details.
*   **User-Friendly Interface:** Built with **Streamlit** for real-time visual feedback and validation verdicts.

## 🛠️ Tech Stack

*   **Python** (Core Logic)
*   **Streamlit** (Frontend UI)
*   **Groq API** (LLM - Llama 3.3)
*   **PyMuPDF (fitz)** (PDF Parsing)
*   **EasyOCR** (Optical Character Recognition)
*   **FPDF** (Demo Data Generation)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/MedbouZZ004/Smart-Assurance-ValidatorX.git
    cd Smart-Assurance-ValidatorX
    ```

2.  **Install dependencies:**
    ```bash
    pip install streamlit pymupdf easyocr groq python-dotenv fpdf
    ```

3.  **Configure Environment:**
    Create a `.env` file in the root directory and add your Groq API key:
    ```env
    GROQ_API_KEY=your_api_key_here
    ```

## ▶️ Usage

1.  **Run the application:**
    ```bash
    streamlit run app.py
    ```

2.  **Upload Documents:**
    *   Drag and drop insurance documents onto the interface.
    *   The system acts as an "AI Auditor", analyzing the file for fraud signs and content validity.

3.  **View Results:**
    *   **Status:** ✅ ACCEPTED or ❌ REJECTED (with score).
    *   **Details:** Extracted fields, detected country, and document type.
    *   **Fraud Alert:** Warnings if suspicious metadata or inconsistencies are found.

## 🧪 Testing

You can generate sample test documents (valid and fraudulent) using the provided script:
```bash
python demo_morocco.py
```
This will create PDF files on your Desktop for testing purposes.


