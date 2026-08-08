
function showLoading(form) {
  const button = form.querySelector("button[type=submit]");
  if (!button) return;
  button.disabled = true;
  const loading = button.querySelector(".loading");
  if (loading) loading.style.display = "inline";
}

document.addEventListener("DOMContentLoaded", () => {
  const stats = window.CIVIC_STATS;
  if (!stats || typeof Chart === "undefined") return;
  const categoryCanvas = document.getElementById("categoryChart");
  const priorityCanvas = document.getElementById("priorityChart");
  if (categoryCanvas) {
    new Chart(categoryCanvas, {
      type: "bar",
      data: {labels: Object.keys(stats.categories), datasets: [{label: "Complaints", data: Object.values(stats.categories)}]},
      options: {responsive: true, plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, ticks: {precision: 0}}}}
    });
  }
  if (priorityCanvas) {
    new Chart(priorityCanvas, {
      type: "doughnut",
      data: {labels: Object.keys(stats.priorities), datasets: [{data: Object.values(stats.priorities)}]},
      options: {responsive: true}
    });
  }
});


async function improveComplaint() {
  const description = document.getElementById("description");
  const location = document.getElementById("location");
  const status = document.getElementById("improveStatus");
  if (!description || description.value.trim().length < 5) {
    if (status) status.textContent = "Write a short complaint first.";
    return;
  }
  if (status) status.textContent = "CivicAI is improving your wording…";
  try {
    const response = await fetch("/api/improve", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({description: description.value, location: location ? location.value : ""})
    });
    const data = await response.json();
    if (data.improved) {
      description.value = data.improved;
      if (status) status.textContent = "Improved. Review the text before submitting.";
    } else if (status) {
      status.textContent = data.error || "AI improvement is unavailable.";
    }
  } catch (error) {
    if (status) status.textContent = "AI improvement is temporarily unavailable.";
  }
}
