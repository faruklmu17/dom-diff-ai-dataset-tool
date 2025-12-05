# 🧠 DOM Diff AI Dataset & Tool  
**A professional-grade toolkit and dataset generator for DOM change detection, UI regression analysis, and AI model training.**

This repository contains the **open-source tooling** used to generate a high-quality, paid DOM Diff dataset hosted on Hugging Face.  
The actual dataset is **not stored here** — only the code and a small example sample are included.  
This prevents copyright issues and keeps the commercial dataset securely protected behind Hugging Face’s paywall.

---

## 🚀 What This Project Is About

Modern AI-powered QA systems need high-quality, human-annotated examples of:

- DOM structure changes  
- UI modifications (colors, text, layout, attributes, IDs)  
- Visual differences between versions  
- Test impact reasoning  
- Suggested new test cases  

This project provides:

### ✔ A **DOM diff generation tool**  
### ✔ A **screenshot generator** using Playwright  
### ✔ A **professional annotation schema** for structured ML training data  
### ✔ A **metadata schema** for filtering and analysis  
### ✔ A **sample dataset entry** to demonstrate structure  
### ✔ A pipeline to create a **commercial, sellable dataset**  

If you are building AI agents for UI testing, visual regression, or DOM understanding — this toolkit gives you the foundation.

---

## 📂 Repository Structure

```
dom-diff-ai-dataset-tool/
  README.md
  LICENSE
  scripts/
    generate_screenshots.py
    diff_engine.py
  schemas/
    annotation_schema.json
    metadata_schema.json
  examples/
    sample_001/
      before.html
      after.html
      annotation.json
      metadata.json
```

---

## 🔒 Where Is the Full Dataset?

The full dataset is located on Hugging Face as a **paid dataset** to protect intellectual property and annotation labor.

### 👉 Why not store data on GitHub?
- GitHub is public → anyone can download your work  
- Hugging Face paid datasets lock downloads behind a secure paywall  
- This allows monetization while keeping the repo fully open-source  

---

## 🛠️ Tooling Included

### **1. Screenshot Generator (Playwright)**
Automatically loads your before/after HTML files and produces:

- `before.png`
- `after.png`
- Auto-filled `metadata.json`

Run:

```bash
pip install playwright
playwright install
python scripts/generate_screenshots.py
```

---

### **2. Annotation Schema**
Defines the structure for human-labeled DOM change reasoning:

```json
{
  "dom_changes": [],
  "change_categories": [],
  "test_impact_analysis": [],
  "new_tests_recommended": []
}
```

---

### **3. Metadata Schema**
Machine-friendly fields for:

- Page type  
- Change counts  
- Creation timestamps  
- Sample IDs  
- DOM versioning  

---

## 📘 Example Sample

A tiny example (`sample_001`) is included for educational purposes only.

---

## 🧭 Roadmap

### **Phase 1 (Current)**
- ✔ Basic screenshot generator  
- ✔ Sample DOM templates  
- ✔ Annotation + metadata schema  
- ✔ Repo structure + documentation  

### **Phase 2**
- ☐ Advanced diff engine  
- ☐ LLM-based annotation draft generator  
- ☐ CLI tool `domdiff-cli`  
- ☐ Hugging Face dataset v1 release  

### **Phase 3**
- ☐ MCP tool integration  
- ☐ Pro dataset versions  
- ☐ API for DOM diff analysis  
- ☐ Full AI model fine-tuning  

---

## 📄 License

All **code** in this repository is MIT licensed.  
The **dataset** hosted on Hugging Face is commercial and separately licensed.

---

## 🤝 Contributing

Contributions to the **tooling** are welcome!  
Dataset contributions are restricted due to licensing requirements.

---

### Made with ❤️ to improve the future of AI-driven software testing.
