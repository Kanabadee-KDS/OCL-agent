# Developer Prompt: Curriculum Document Extraction & Management Web Application

> ต้นฉบับจากเจ้าของโปรเจก (20 ต.ค. 2569) เก็บไว้เป็น spec อ้างอิง
> ข้อที่ขัดกับข้อจำกัดของ server on-prem ถูกปรับใน `docs/decisions.md` (เฟส 1)

**Role:**
Act as an Expert Full-Stack Developer and AI Integration Specialist. Your task is to build a "Curriculum Document Extraction & Management Web Application".

## Tech Stack (Recommended)
*   **Frontend:** Next.js (React), Tailwind CSS, Markdown Editor (e.g., MDEditor, Toast UI Editor)
*   **Backend:** Python (FastAPI) - For document processing, AI orchestration, and file system management.
*   **AI Integration:** LangChain or LlamaIndex.
*   **AI Models:** Google Gemini API (Cloud) and Gemma (Local AI via Ollama).
*   **Storage:** Local File System (for `.md` and images).
*   **Authentication & Database:** NextAuth.js (Frontend) + SQLite/PostgreSQL (for user credentials and roles).

---

## 1. Core Workflows & Features

### 1.1. Authentication & Authorization (Role-Based Access)
*   Implement a secure Login system.
*   Define at least two user roles:
    *   **Admin / Editor:** Can upload files, run AI extraction, edit Markdown files, and save changes.
    *   **Viewer:** Can only browse and read the extracted curriculum documents.

### 1.2. File Upload & AI Model Toggle
*   Create a Dashboard with a drag-and-drop zone for PDF and Word (`.docx`) files.
*   **AI Provider Toggle:** Provide a UI switch or dropdown for the user to select the AI engine before extracting:
    *   Option A: **Gemini (Cloud)** (Fast, high accuracy via API).
    *   Option B: **Local AI (Gemma latest version)** (Privacy-focused, running locally via Ollama or similar local inference server).
*   Display a real-time progress bar or status indicator during parsing and extraction.

### 1.3. AI Extraction Pipeline (Backend)
*   **Document Parsing:** Read text and extract images/diagrams from the uploaded PDF/Word document.
*   **Data Extraction:** Send the parsed text to the selected LLM (Gemini or Local Gemma) using a structured prompt to extract specific curriculum sections.
*   **Fallback Handling:** If the AI fails to extract a specific section, generate a template `.md` file with placeholder headings so the user can fill it in manually.

### 1.4. Local File System Storage
*   All extracted data must be converted to Markdown (`.md`).
*   Save files directly to the server's local directory (e.g., `/server_data/curriculums/{program_name}_{year}/`).
*   Extracted images/diagrams must be saved in an `assets/` subfolder within the specific curriculum's directory.

### 1.5. Document Management & Editor UI
*   **Sidebar Layout:** List all uploaded and processed curriculums. Clicking a curriculum expands a sub-menu showing its `.md` files.
*   **Main Content Area:**
    *   **Preview Mode:** Render the Markdown beautifully (including images referenced from the local `assets/` folder).
    *   **Edit Mode (Admin only):** A rich Markdown editor toolbar.
*   **Save Functionality:** A "Save" button to overwrite the specific `.md` file on the server's local storage. Use optimistic UI updates and handle state management (e.g., via Zustand or React Context) to prevent data loss before saving.

---

## 2. Data Extraction Template & File Structure

The AI must extract and organize the data into the following `.md` files per curriculum:

1.  `1-program_info.md`: Program Name, Year, Total Credits.
2.  `2-course_structure.md`: Curriculum structure and categories (e.g., General Education, Core Courses, Electives).
3.  `3-courses_list.md`: Course Codes, Course Names (TH/EN), and Course Descriptions.
4.  `4-plos.md`: Program Learning Outcomes (PLOs) and Sub-PLOs.
5.  `5-curriculum_mapping.md`: Curriculum Mapping (Must be formatted as a Markdown Table).
6.  `6-study_plan.md`: Study plan grouped by academic year and semester.
7.  `assets/`: Directory for storing extracted images and diagrams. The `.md` files must reference these images using relative paths (e.g., `![diagram_1](./assets/diagram_1.png)`).

---

## 3. Specific Implementation Instructions
1.  **AI Orchestration:** Write clear system prompts for both Gemini and Gemma to ensure output consistency. Be mindful of context window limits, especially for Local Gemma; implement text chunking (RAG or Map-Reduce) if the curriculum document is too large.
2.  **Local API Server:** Provide instructions or a `docker-compose.yml` snippet on how to spin up the Local Gemma model (e.g., using Ollama container) alongside the FastAPI backend.
3.  **Image Serving:** FastAPI must serve the local `assets/` folder as a static directory so the Next.js frontend can render the images inside the Markdown preview.

Please generate the project structure, essential boilerplate code (Next.js frontend, FastAPI backend, NextAuth setup), and the specific LangChain/LLM routing logic for the Gemini/Gemma toggle.
