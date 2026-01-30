Life Savings & Succession Document Validator
Overview

This project is an intelligent document validation system designed for life savings insurance (épargne-vie) in a succession context.
Its goal is to automatically analyze, verify, and validate insurance claim documents after a death, while detecting inconsistencies, missing data, or potential fraud.

The system accelerates processing for valid cases and safely redirects complex or suspicious cases to a human reviewer.



Problem Context

In life insurance and savings contracts, claim processing after a death is often slow and manual. Files usually contain multiple documents, and errors or fraud can lead to financial loss, legal issues, or delays for beneficiaries.

This project addresses these challenges by automating the first level of document analysis, while keeping humans in the loop for final decisions when needed.



What the System Does

The system receives a case file composed of multiple documents (PDF, PNG, JPEG).
It then:

identifies the type of each document

reads and extracts the relevant information

compares data across documents

detects inconsistencies or suspicious elements

decides whether the case can be validated automatically or must be reviewed by a human agent




Documents Supported (Succession / Épargne-Vie)

The system is designed to handle the following documents:

National ID of the deceased (CIN / Passport)

Death certificate or death record

Life savings insurance contract (épargne-vie / policy)

Beneficiary clause or contract amendment

National ID of the beneficiary

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

