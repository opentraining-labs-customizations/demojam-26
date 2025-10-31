Here is the complete content for a single-page GitHub repository README file. You can copy and paste this directly into your `README.md` file.

-----

# 🧠 Ansible Playbook Mind Map Viewer (Flask + Vis-Network)

This project is a simple Flask application designed to visualize the output of an Ansible playbook—whether raw text logs or structured JSON results—as an **interactive, hierarchical mind map**. It also provides auxiliary outputs, including nested JSON, a Markdown list, and an analysis of the **Top 20 Time-Consuming Tasks** for performance optimization.

The visualization is powered by the **`vis-network`** JavaScript library, providing a stable, tree-like view of your Play $\rightarrow$ Task $\rightarrow$ Host structure.

-----

## 🚀 Features

  * **File Upload:** Accepts Ansible playbook output files (`.json` or `.txt`).
  * **Mind Map Visualization:** Converts Ansible plays, tasks, and host results into a **stable, hierarchical network graph**.
  * **Interactive Expansion:** The map starts collapsed, allowing users to **click nodes to expand/collapse** details.
  * **Task Performance Analysis:** Extracts and lists the **Top 20 Time-Consuming Tasks** based on duration data in the input.
  * **Multiple Outputs:** Generates **Nested JSON** and a **Markdown List** representation of the playbook structure.

-----

## 📋 Installation and Setup

This project requires Python and Flask.

### 1\. Prerequisites

  * Python 3.6+
  * **`Flask`** (will be installed below)

### 2\. Project Files

Ensure you have the following three files in your repository directory:

  * `app.py` (The Flask backend code)
  * `index.html` (The frontend code)
  * `requirements.txt` (Contains `Flask`)

### 3\. Install Dependencies

-> The `requirements.txt` file has dependencies. 

### 4\. Run the Application

Execute the Python script:

```bash
python app.py
```

### 5\. Access the Viewer

Open your web browser and navigate to:

```
http://127.0.0.1:5000/
```

-----

## 💾 Code Content Summary

### `app.py` (Flask Backend)

This file contains the core logic:

  * Parses uploaded text logs (`.txt`) or structured JSON (`.json`) into a normalized Python dictionary.
  * The `build_mindmap_from_ansible` function converts this structure into `nodes`, `edges`, `nested_json`, and `markdown`.
  * The `get_top_time_consuming_tasks` function analyzes the parsed data for task durations.
  * The `/upload` route handles the file, runs both the mind map generation and top task analysis, and returns a single JSON payload.

### `index.html` (Frontend)

This file is a single HTML page that:

  * Includes the **`vis-network`** library for graphing.
  * Uses a **Hierarchical Layout** (`hierarchical: { enabled: true }`) and **disables physics** (`physics: { enabled: false }`) to ensure the mind map is stable and non-overlapping.
  * Handles the form submission and fetches data from the `/upload` endpoint.
  * Renders the interactive graph and displays the **Nested JSON**, **Markdown List**, and **Top 20 Tasks**.

-----
