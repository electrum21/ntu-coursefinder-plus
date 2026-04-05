# NTU GEM CourseFinder+

NTU GEM CourseFinder+ is a specialized data aggregation and visualization tool designed to streamline the exchange planning process for NTU students. By consolidating data from various partner universities into a single, unified interface, this application eliminates the manual overhead typically associated with researching course equivalencies and past credit transfer approvals.

---

## Core Features

### 1. Multi-University Data Aggregation
Unlike the standard interface which requires per-university queries, CourseFinder+ enables bulk scraping. Users can select multiple countries and partner institutions simultaneously, retrieving all relevant course matching records in a single operation.

### 2. Dynamic Advanced Filtering
The platform provides a robust filtering engine that allows users to parse through thousands of records instantaneously. You can refine results by:
* **NTU Course Specifics:** Filter by course code prefixes (e.g. MH, CZ, SC) or course titles.
* **Approval Parameters:** Sort by approval status, academic year, or specific semesters.
* **Institutional Data:** Narrow down results by host country or specific partner universities.

### 3. Integrated Detail Viewer
To facilitate deeper research, the tool features an inline expansion system. Users can view comprehensive course details—including student comments, assessment breakdowns, contact hours, and syllabus information—without navigating away from the main table.

### 4. Portability & Export
For offline planning and long-term documentation, the application includes a one-click CSV export feature. This allows students to transition their research into personalized spreadsheets for final module mapping submissions.

---

## Technical Specifications

### System Requirements
* **Environment:** Python 3.9 or higher
* **Dependencies:** Flask, Beautiful Soup 4, Requests

### Installation & Deployment
1.  **Clone the repository** and navigate to the project directory.
2.  **Install dependencies:**
    ```bash
    pip install flask requests beautifulsoup4
    ```
3.  **Initialize the local server:**
    ```bash
    python server.py
    ```
4.  **Access the interface:** Navigate to `http://localhost:5000` in your web browser.

---

## Usage Workflow

1.  **Authentication:** Sign in using your NTU Student ID and network credentials to access the secure database.
2.  **Selection:** Define your search scope by selecting the target countries and their respective universities.
3.  **Data Retrieval:** Execute the **Scrape** command. The tool includes built-in request delays to ensure respectful interaction with institutional servers.
4.  **Analysis:** Use the global search bar and column filters to identify viable module matches.
5.  **Export:** Generate a CSV report of your shortlisted courses for administrative reference.

---

## Important Considerations

* **Data Accuracy:** This tool aggregates data identical to the official NTU CourseFinder database. It serves as an interface enhancement rather than an independent data source.
* **Policy Compliance:** Past course approvals do not guarantee future equivalency. All module mappings are subject to final approval by the respective schools and the Office of Global Education and Mobility (OGEM).
* **Scope:** The database generally retains records from the preceding three academic years. If a specific course does not appear, it may indicate that no prior matching request has been formally processed.

---

*Disclaimer: This is an independent student-led project and is not officially affiliated with or endorsed by Nanyang Technological University.*