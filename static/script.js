let currentPage = 1;
let currentStatus = "";
const pageSize = 15;

async function fetchJobs() {
    const tableBody = document.getElementById("jobs-list");
    const totalCount = document.getElementById("total-count");
    const pageDisplay = document.getElementById("current-page");
    const totalPagesDisplay = document.getElementById("total-pages");

    let url = `/api/async/embedding/jobs?page=${currentPage}&size=${pageSize}`;
    if (currentStatus) url += `&status=${currentStatus}`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        totalCount.textContent = data.total;
        pageDisplay.textContent = data.page;
        totalPagesDisplay.textContent = data.pages || 1;

        document.getElementById("prev-page").disabled = data.page <= 1;
        document.getElementById("next-page").disabled = data.page >= data.pages;

        tableBody.innerHTML = "";

        data.items.forEach(job => {
            const row = document.createElement("tr");

            const date = new Date(job.created_at).toLocaleString();

            row.innerHTML = `
                <td class="job-id">${job.job_id.substring(0, 8)}...</td>
                <td>
                    <div class="date">${date}</div>
                    <div class="file-name">${job.filename || job.input_checksum.substring(0, 8)}</div>
                </td>
                <td><span class="status-badge status-${job.status}">${job.status}</span></td>
                <td>
                    <div class="progress-group">
                        <div class="progress-container">
                            <div class="progress-fill" style="width: ${job.progress}%"></div>
                        </div>
                        <span class="progress-text">${job.progress}%</span>
                    </div>
                </td>
                <td>
                    ${job.status === 'failed' ? `<small style="color:red" title="${job.error_message}">Error</small>` : ''}
                    ${job.status === 'done' ? `<small title="Dim: ${job.vector_dim}">${job.chunk_count} chunks</small>` : ''}
                </td>
            `;
            tableBody.appendChild(row);
        });
    } catch (err) {
        console.error("Failed to fetch jobs:", err);
    }
}

// Initial fetch and setup
document.addEventListener("DOMContentLoaded", () => {
    fetchJobs();

    // Auto refresh
    setInterval(() => {
        if (currentPage === 1) fetchJobs();
    }, 5000);

    // Filter clicks
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentStatus = btn.dataset.status;
            currentPage = 1;
            fetchJobs();
        });
    });

    // Pagination
    document.getElementById("prev-page").addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            fetchJobs();
        }
    });

    document.getElementById("next-page").addEventListener("click", () => {
        currentPage++;
        fetchJobs();
    });

    document.getElementById("refresh-btn").addEventListener("click", () => {
        fetchJobs();
    });
});
