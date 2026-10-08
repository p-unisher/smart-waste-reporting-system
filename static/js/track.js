// Track report

document.getElementById("trackForm").addEventListener("submit", function(event) {

    event.preventDefault();

    let reportId = document.getElementById("reportId").value;

    let result = document.getElementById("result");


    if (reportId == "") {

        result.innerHTML = "Please enter your Report ID.";

    } else {

        result.innerHTML =
            "Your report is currently under review.";

        // Later Flask will get the
        // actual status from SQLite.

    }

});