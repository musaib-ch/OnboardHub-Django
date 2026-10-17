document.addEventListener("DOMContentLoaded", function () {
    var checklist = document.getElementById("interactive-checklist");
    if (!checklist) return;

    checklist.querySelectorAll("input[type=checkbox]").forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
            var row = checkbox.closest(".task-row");
            if (row) row.classList.toggle("is-complete", checkbox.checked);
        });
    });
});